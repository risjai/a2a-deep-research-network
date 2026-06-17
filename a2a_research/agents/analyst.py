"""Analyst specialist: synthesizes source material into a research brief.

Uses Gemini via :mod:`a2a_research.gemini`, which degrades to a deterministic
stub when no API key is set. This is a pure a2a-sdk server — it does NOT import
google.adk.
"""

from a2a.server.agent_execution import RequestContext
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Part,
    TextPart,
)

from .. import config, gemini
from ..executor_base import ProgressFn, ResearchExecutor

_PROMPT = (
    "You are a research analyst. From the material below, produce a concise "
    "research brief as 3-5 bullet points capturing the key findings. Use only "
    "the provided material; do not invent facts.\n\n"
    "Material:\n{material}"
)


class AnalystExecutor(ResearchExecutor):
    """Turns retrieved source material into a 3-5 bullet brief."""

    artifact_name = "brief"

    async def run(
        self, user_input: str, context: RequestContext, progress: ProgressFn
    ) -> list[Part]:
        await progress("Synthesizing a brief from the provided material...")
        prompt = _PROMPT.format(material=user_input)
        brief = await gemini.generate(prompt, stub_label="analysis")
        return [Part(root=TextPart(text=brief))]


def build_card() -> AgentCard:
    """The Analyst's Agent Card (served at /.well-known/agent-card.json)."""
    return AgentCard(
        name="analyst",
        description="Synthesizes retrieved source material into a concise research brief.",
        url=config.base_url("analyst") + "/",
        version="0.1.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="synthesize",
                name="Synthesize brief",
                description="Turn raw sources into a structured brief.",
                tags=["analysis", "synthesis"],
            )
        ],
    )


CARD = build_card()
EXECUTOR = AnalystExecutor()
