"""Critic specialist: fact-checks a brief and surfaces gaps and weak claims.

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
    "You are a research critic. Review the brief below and list its gaps, "
    "caveats, and any claims that need a citation. Be specific and concise.\n\n"
    "Brief:\n{material}"
)


class CriticExecutor(ResearchExecutor):
    """Identifies gaps, caveats, and unsupported claims in a brief."""

    artifact_name = "critique"

    async def run(
        self, user_input: str, context: RequestContext, progress: ProgressFn
    ) -> list[Part]:
        await progress("Reviewing the brief for gaps and weak claims...")
        prompt = _PROMPT.format(material=user_input)
        critique = await gemini.generate(prompt, stub_label="critique")
        return [Part(root=TextPart(text=critique))]


def build_card() -> AgentCard:
    """The Critic's Agent Card (served at /.well-known/agent-card.json)."""
    return AgentCard(
        name="critic",
        description="Fact-checks a brief and surfaces gaps, caveats, and unsupported claims.",
        url=config.base_url("critic") + "/",
        version="0.1.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="critique",
                name="Critique brief",
                description="Identify gaps and weak claims in a research brief.",
                tags=["review", "fact-check"],
            )
        ],
    )


CARD = build_card()
EXECUTOR = CriticExecutor()
