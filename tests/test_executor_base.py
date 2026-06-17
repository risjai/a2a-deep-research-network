"""Lifecycle tests for ResearchExecutor.

We drive the executor through the proven in-process A2A round-trip (ASGITransport
+ real EventQueue inside the request handler) rather than hand-building a
RequestContext, so we exercise the same code path production uses. We assert what
the protocol layer actually streams back: a terminal ``completed`` task carrying
the artifact on the happy path, and a terminal ``failed`` task carrying the
exception message when ``run()`` raises.
"""

from a2a.server.agent_execution import RequestContext
from a2a.types import DataPart, Part, TaskState, TextPart

from a2a_research.executor_base import ProgressFn, ResearchExecutor


def _trivial_card():
    """A minimal valid card; built lazily to avoid import-time SDK coupling."""
    from a2a.types import AgentCapabilities, AgentCard, AgentSkill

    return AgentCard(
        name="trivial",
        description="A trivial test executor.",
        url="http://test/",
        version="0.1.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(id="echo", name="echo", description="echoes", tags=["test"])
        ],
    )


class _EchoExecutor(ResearchExecutor):
    """Trivial subclass: returns the user input as a single TextPart artifact."""

    artifact_name = "echo"

    async def run(
        self, user_input: str, context: RequestContext, progress: ProgressFn
    ) -> list[Part]:
        return [Part(root=TextPart(text=f"echo:{user_input}"))]


class _DataExecutor(ResearchExecutor):
    """Returns a structured DataPart, proving the structured artifact round-trips."""

    artifact_name = "payload"

    async def run(
        self, user_input: str, context: RequestContext, progress: ProgressFn
    ) -> list[Part]:
        return [Part(root=DataPart(data={"received": user_input}))]


class _BoomExecutor(ResearchExecutor):
    """run() always raises, so the base must mark the task failed."""

    async def run(
        self, user_input: str, context: RequestContext, progress: ProgressFn
    ) -> list[Part]:
        raise ValueError("intentional boom")


class TestResearchExecutorHappyPath:
    async def it_completes_and_emits_the_text_artifact(self, a2a_roundtrip):
        tasks = await a2a_roundtrip(_trivial_card(), _EchoExecutor(), "hello world")

        final = tasks[-1]
        assert final.status.state == TaskState.completed
        assert final.artifacts, "expected at least one artifact on a completed task"
        artifact = final.artifacts[0]
        assert artifact.name == "echo"
        assert artifact.parts[0].root.text == "echo:hello world"

    async def it_round_trips_a_structured_datapart_artifact(self, a2a_roundtrip):
        tasks = await a2a_roundtrip(_trivial_card(), _DataExecutor(), "topic-x")

        final = tasks[-1]
        assert final.status.state == TaskState.completed
        assert final.artifacts[0].parts[0].root.data == {"received": "topic-x"}


class TestResearchExecutorFailurePath:
    async def it_marks_the_task_failed_when_run_raises(self, a2a_roundtrip):
        tasks = await a2a_roundtrip(_trivial_card(), _BoomExecutor(), "anything")

        final = tasks[-1]
        assert final.status.state == TaskState.failed
        # The base class surfaces a readable failure message on the task status.
        message = final.status.message
        assert message is not None, "failed task should carry an explanatory message"
        text = " ".join(part.root.text for part in message.parts)
        assert "ValueError" in text
        assert "intentional boom" in text

    async def it_does_not_attach_an_artifact_on_failure(self, a2a_roundtrip):
        tasks = await a2a_roundtrip(_trivial_card(), _BoomExecutor(), "anything")

        final = tasks[-1]
        assert not final.artifacts
