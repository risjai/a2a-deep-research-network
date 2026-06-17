"""ADK host orchestrator.

The host is a Google ADK ``LlmAgent`` that knows nothing about the specialists'
code — it discovers each one purely through its Agent Card URL and wires them in
as ``RemoteA2aAgent`` *sub-agents*. ``RemoteA2aAgent`` subclasses ``BaseAgent``,
so it belongs in ``sub_agents=[...]`` (LLM-driven delegation/transfer), never in
``tools=[...]``.

Running the host requires a Gemini key (it is itself an LLM agent) and the three
specialist servers to be reachable at their card URLs.
"""

from collections.abc import AsyncIterator

from google.adk.agents import LlmAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .. import config

_INSTRUCTION = (
    "You coordinate a deep-research task across specialist agents. Steps:\n"
    "1. Transfer to `retriever` with the research topic to gather Wikipedia sources.\n"
    "2. Transfer to `analyst` with the topic and the gathered sources to get a brief.\n"
    "3. Transfer to `critic` with the brief to surface gaps and weak claims.\n"
    "4. Compose a final report that combines the brief and the critique.\n"
    "Always delegate via your sub-agents; never invent sources or findings."
)

_APP_NAME = "a2a_research"
_USER_ID = "local-user"


def build_host() -> LlmAgent:
    """Build the orchestrator with the three specialists wired as sub-agents."""
    return LlmAgent(
        name="host",
        model=config.MODEL,
        description="Research orchestrator that delegates to specialist A2A agents.",
        instruction=_INSTRUCTION,
        sub_agents=[
            RemoteA2aAgent(
                name="retriever",
                agent_card=config.card_url("retriever"),
                description="Gathers source material on a topic from Wikipedia.",
            ),
            RemoteA2aAgent(
                name="analyst",
                agent_card=config.card_url("analyst"),
                description="Synthesizes source material into a research brief.",
            ),
            RemoteA2aAgent(
                name="critic",
                agent_card=config.card_url("critic"),
                description="Fact-checks a brief and surfaces gaps.",
            ),
        ],
    )


async def stream_query(question: str) -> AsyncIterator[tuple[str, str, bool]]:
    """Run a research question through the host, yielding (author, text, is_final).

    Each yielded tuple is one ADK event that carried text: which agent produced
    it, the text, and whether it is the final response. Lets the CLI show the
    delegation unfolding live.
    """
    host = build_host()
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=_APP_NAME, user_id=_USER_ID
    )
    runner = Runner(
        agent=host, app_name=_APP_NAME, session_service=session_service
    )
    message = types.Content(role="user", parts=[types.Part(text=question)])
    async for event in runner.run_async(
        user_id=_USER_ID, session_id=session.id, new_message=message
    ):
        text = _event_text(event)
        if text:
            yield event.author or "host", text, event.is_final_response()


def _event_text(event) -> str:
    """Concatenate any text parts on an ADK event (empty string if none)."""
    if not event.content or not event.content.parts:
        return ""
    return "".join(part.text for part in event.content.parts if part.text)
