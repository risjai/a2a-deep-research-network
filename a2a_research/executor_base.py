"""Shared A2A task-lifecycle base for the specialist agents.

A2A models every request as a *task* that moves through states:
``submitted -> working -> completed`` (or ``failed``). Driving that lifecycle is
identical boilerplate for all three specialists, so it lives here once. A
subclass only implements :meth:`run`, returning the artifact parts to emit.
"""

from abc import ABC, abstractmethod

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TextPart


class ResearchExecutor(AgentExecutor, ABC):
    """Owns the A2A task lifecycle; subclasses supply the domain logic in run()."""

    #: Name attached to the emitted artifact (override per specialist).
    artifact_name: str = "result"

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.submit()  # task acknowledged
        await updater.start_work()  # state -> working
        try:
            user_input = context.get_user_input()
            parts = await self.run(user_input, context)
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
    async def run(self, user_input: str, context: RequestContext) -> list[Part]:
        """Produce the artifact parts for this request.

        Raise on failure; the base class converts the exception into a failed task.
        """
