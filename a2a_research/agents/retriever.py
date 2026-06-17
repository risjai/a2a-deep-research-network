"""Retriever specialist: gathers source material from Wikipedia.

This is the CI-safe agent: it uses NO LLM and needs no API key, so it fully
exercises the A2A protocol layer (task lifecycle + structured artifact) on its
own. It searches Wikipedia for a topic and returns the top summaries as a
structured ``DataPart``.
"""

import asyncio
from collections.abc import Awaitable, Callable
from urllib.parse import quote

import httpx

from a2a.server.agent_execution import RequestContext
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    DataPart,
    Part,
)

from .. import config
from ..executor_base import ProgressFn, ResearchExecutor

_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_HEADERS = {"User-Agent": "a2a-research/0.1 (demo)"}
_TOP_N = 3


async def fetch_sources(
    topic: str,
    on_titles: Callable[[list[str]], Awaitable[None]] | None = None,
) -> list[dict]:
    """Search Wikipedia for ``topic`` and return up to 3 summarized sources.

    If ``on_titles`` is given it is awaited once with the matched titles, before
    the summaries are fetched — the Retriever uses this to stream progress.
    Returns an empty list if there are no search hits (a valid empty result,
    not an error). Raises on network/HTTP failure.
    """
    async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0) as client:
        search = await client.get(
            _SEARCH_URL,
            params={
                "action": "query",
                "list": "search",
                "srsearch": topic,
                "format": "json",
            },
        )
        search.raise_for_status()
        hits = search.json().get("query", {}).get("search", [])
        titles = [hit["title"] for hit in hits[:_TOP_N]]
        if not titles:
            return []
        if on_titles is not None:
            await on_titles(titles)

        # Fetch summaries concurrently; one title failing (e.g. a 404 on a
        # redirect) shouldn't sink the whole retrieval, so drop failures.
        results = await asyncio.gather(
            *(_fetch_summary(client, title) for title in titles),
            return_exceptions=True,
        )
        return [r for r in results if isinstance(r, dict)]


async def _fetch_summary(client: httpx.AsyncClient, title: str) -> dict:
    """Fetch one page summary, guarding missing keys."""
    resp = await client.get(_SUMMARY_URL.format(title=quote(title, safe="")))
    resp.raise_for_status()
    data = resp.json()
    url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
    return {
        "title": data.get("title", title),
        "extract": data.get("extract", ""),
        "url": url,
    }


class RetrieverExecutor(ResearchExecutor):
    """Returns Wikipedia sources for a topic as a structured DataPart."""

    artifact_name = "wikipedia_sources"

    async def run(
        self, user_input: str, context: RequestContext, progress: ProgressFn
    ) -> list[Part]:
        await progress(f"Searching Wikipedia for '{user_input}'...")

        async def _announce(titles: list[str]) -> None:
            await progress(f"Found {len(titles)} pages: {', '.join(titles)}. Fetching summaries...")

        sources = await fetch_sources(user_input, on_titles=_announce)
        await progress(f"Retrieved {len(sources)} sources.")
        return [
            Part(
                root=DataPart(
                    data={
                        "topic": user_input,
                        "sources": sources,
                        "source_count": len(sources),
                    }
                )
            )
        ]


def build_card() -> AgentCard:
    """The Retriever's Agent Card (served at /.well-known/agent-card.json)."""
    return AgentCard(
        name="retriever",
        description="Gathers source material on a topic from Wikipedia.",
        url=config.base_url("retriever") + "/",
        version="0.1.0",
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["text/plain"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(
                id="wikipedia_lookup",
                name="Wikipedia lookup",
                description="Search Wikipedia and return summaries for a topic.",
                tags=["research", "wikipedia"],
                examples=["quantum computing", "the French Revolution"],
            )
        ],
    )


CARD = build_card()
EXECUTOR = RetrieverExecutor()
