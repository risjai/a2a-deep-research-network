"""Tests for the ADK host orchestrator's plumbing — no API key, no network.

These cover *our* glue, not the real LLM or live A2A delegation: session setup,
the ``Runner.run_async`` loop, ``is_final_response`` handling, and the
``_event_text`` part-concatenation. We swap in a fake ``BaseLlm`` that returns a
fixed text response. Because that response carries no function-call parts, ADK
treats it as the host answering directly and never transfers to a
``RemoteA2aAgent`` — so no specialist servers need to be running.

The live LLM-driven delegation path (host actually calling the three A2A
specialists) is out of scope here; it requires a Gemini key and running servers.
"""

import warnings

import pytest
from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm, LlmResponse
from google.genai import types

import a2a_research.host.orchestrator as orchestrator

# RemoteA2aAgent emits an [EXPERIMENTAL] warning at construction; irrelevant here.
warnings.filterwarnings("ignore", message=".*RemoteA2aAgent.*")

_REPLY = "Final research report: synthesized brief plus critique."


class _FakeModel(BaseLlm):
    """A BaseLlm that yields one fixed text turn (no tool calls => answer directly)."""

    reply: str = _REPLY

    async def generate_content_async(self, llm_request, stream: bool = False):
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=self.reply)])
        )


@pytest.fixture
def fake_host(monkeypatch):
    """Patch build_host() to use the fake model and no sub-agents (zero network)."""

    def _build() -> LlmAgent:
        return LlmAgent(
            name="host",
            model=_FakeModel(model="fake"),
            description="test host",
            instruction="ignored by the fake model",
        )

    monkeypatch.setattr(orchestrator, "build_host", _build)


class TestStreamQuery:
    async def it_yields_a_final_response_with_the_model_text(self, fake_host):
        events = [item async for item in orchestrator.stream_query("a question")]

        assert events, "expected at least one event"
        author, text, is_final = events[-1]
        assert is_final is True
        assert author == "host"
        assert text == _REPLY

    async def it_only_yields_events_that_carry_text(self, fake_host):
        # Every yielded tuple must have non-empty text (the contract the CLI relies on).
        async for _author, text, _is_final in orchestrator.stream_query("q"):
            assert text


class TestEventText:
    """Unit tests for the pure _event_text helper (no model involved)."""

    def it_concatenates_multiple_text_parts(self):
        content = types.Content(
            role="model",
            parts=[types.Part(text="Hello "), types.Part(text="world")],
        )
        event = _make_event(content)
        assert orchestrator._event_text(event) == "Hello world"

    def it_returns_empty_string_when_there_is_no_content(self):
        assert orchestrator._event_text(_make_event(None)) == ""

    def it_ignores_non_text_parts(self):
        # A part with no text (text=None) should contribute nothing, not crash.
        content = types.Content(
            role="model", parts=[types.Part(text=None), types.Part(text="kept")]
        )
        assert orchestrator._event_text(_make_event(content)) == "kept"


def _make_event(content):
    """Minimal stand-in with the .content attribute _event_text reads."""

    class _Event:
        def __init__(self, content):
            self.content = content

    return _Event(content)
