"""Shared A2A task-lifecycle base for the specialist agents.

A2A models every request as a *task* that moves through states:
``submitted -> working -> completed`` (or ``failed``). Driving that lifecycle is
identical boilerplate for all three specialists, so it lives here once. A
subclass only implements :meth:`run`, returning the artifact parts to emit.
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TaskState, TextPart

#: A request-scoped callback a specialist can call to stream an interim progress
#: note to the client (as a ``working`` status update). Awaitable.
ProgressFn = Callable[[str], Awaitable[None]]


class ResearchExecutor(AgentExecutor, ABC):
    """Owns the A2A task lifecycle; subclasses supply the domain logic in run().

    A2A lets an agent stream interim ``working`` status updates before it
    finishes. The base hands :meth:`run` a request-scoped ``progress`` callback
    for exactly that. The callback closes over this request's ``TaskUpdater`` and
    is never stored on ``self`` — these executors are shared singletons, so
    per-request state must stay local to keep concurrent requests isolated.
    """

    #: Name attached to the emitted artifact (override per specialist).
    artifact_name: str = "result"

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.submit()  # task acknowledged
        await updater.start_work()  # state -> working

        async def progress(text: str) -> None:
            """Emit an interim 'working' status update visible to streaming clients."""
            await updater.update_status(
                TaskState.working,
                message=updater.new_agent_message([Part(root=TextPart(text=text))]),
            )

        try:
            user_input = context.get_user_input()
            parts = await self.run(user_input, context, progress)
            await updater.add_artifact(parts, name=self.artifact_name)
            await updater.complete()  # terminal: completed
        except Exception as exc:  # surface a readable failure to the caller
            message = updater.new_agent_message(
                [Part(root=TextPart(text=f"{type(exc).__name__}: {exc}"))]
            )
            await updater.failed(message=message)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()

    @abstractmethod
    async def run(
        self, user_input: str, context: RequestContext, progress: ProgressFn
    ) -> list[Part]:
        """Produce the artifact parts for this request.

        Call ``await progress(text)`` to stream interim updates. Raise on failure;
        the base class converts the exception into a failed task.
        """
