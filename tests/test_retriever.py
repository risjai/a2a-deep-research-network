"""Retriever tests — Wikipedia client logic plus the A2A artifact shape.

No real network is ever touched: ``fetch_sources`` is unit-tested against a fake
``httpx.AsyncClient`` that returns canned search/summary JSON, and the executor
round-trip patches ``fetch_sources`` itself to canned data. The fake mirrors the
real call shape: an async context manager whose ``get(url, params=...)`` returns
a response with ``raise_for_status()`` and ``json()``.
"""

import httpx
import pytest

from a2a.types import TaskState

from a2a_research.agents import retriever


# --- fake httpx plumbing -------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient: routes search vs. summary by URL."""

    def __init__(self, search_payload, summary_by_title, **_kwargs):
        self._search_payload = search_payload
        self._summary_by_title = summary_by_title

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        if url == retriever._SEARCH_URL:
            return _FakeResponse(self._search_payload)
        # summary URL: extract the title from the formatted path
        prefix = retriever._SUMMARY_URL.split("{title}")[0]
        title = url[len(prefix):]
        return _FakeResponse(self._summary_by_title[title])


def _patch_httpx(monkeypatch, search_payload, summary_by_title):
    """Replace retriever.httpx.AsyncClient with a fake bound to canned data."""

    def _factory(**kwargs):
        return _FakeAsyncClient(search_payload, summary_by_title, **kwargs)

    monkeypatch.setattr(retriever.httpx, "AsyncClient", _factory)


def _search(*titles):
    return {"query": {"search": [{"title": t} for t in titles]}}


def _summary(title, extract="ex", page_url="http://example/page"):
    return {
        "title": title,
        "extract": extract,
        "content_urls": {"desktop": {"page": page_url}},
    }


# --- fetch_sources unit tests --------------------------------------------


class TestFetchSources:
    async def it_parses_the_top_three_titles(self, monkeypatch):
        search = _search("Alpha", "Beta", "Gamma", "Delta", "Epsilon")
        summaries = {
            t: _summary(t) for t in ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
        }
        _patch_httpx(monkeypatch, search, summaries)

        sources = await retriever.fetch_sources("anything")

        assert [s["title"] for s in sources] == ["Alpha", "Beta", "Gamma"]

    async def it_builds_a_source_dict_with_title_extract_and_url(self, monkeypatch):
        search = _search("Alpha")
        summaries = {"Alpha": _summary("Alpha", "an extract", "http://wiki/Alpha")}
        _patch_httpx(monkeypatch, search, summaries)

        sources = await retriever.fetch_sources("anything")

        assert sources == [
            {"title": "Alpha", "extract": "an extract", "url": "http://wiki/Alpha"}
        ]

    async def it_defaults_url_to_empty_when_content_urls_missing(self, monkeypatch):
        search = _search("Alpha")
        # summary missing content_urls entirely -> url guard must yield ""
        summaries = {"Alpha": {"title": "Alpha", "extract": "ex"}}
        _patch_httpx(monkeypatch, search, summaries)

        sources = await retriever.fetch_sources("anything")

        assert sources[0]["url"] == ""
        assert sources[0]["title"] == "Alpha"
        assert sources[0]["extract"] == "ex"

    async def it_returns_empty_list_when_no_search_hits(self, monkeypatch):
        _patch_httpx(monkeypatch, _search(), {})

        sources = await retriever.fetch_sources("nothing matches")

        assert sources == []


# --- executor round-trip (no network, no key) ----------------------------


class TestRetrieverExecutorRoundTrip:
    @pytest.fixture(autouse=True)
    def _stub_fetch(self, monkeypatch):
        async def _fake_fetch(topic, on_titles=None):
            if on_titles is not None:
                await on_titles(["Quantum computing", "Qubit"])
            return [
                {"title": "Quantum computing", "extract": "qc", "url": "http://q"},
                {"title": "Qubit", "extract": "a qubit", "url": "http://qb"},
            ]

        monkeypatch.setattr(retriever, "fetch_sources", _fake_fetch)

    async def it_completes_with_a_datapart_carrying_topic_and_sources(
        self, a2a_roundtrip
    ):
        tasks = await a2a_roundtrip(
            retriever.CARD, retriever.RetrieverExecutor(), "quantum computing"
        )

        final = tasks[-1]
        assert final.status.state == TaskState.completed

        data = final.artifacts[0].parts[0].root.data
        assert data["topic"] == "quantum computing"
        assert data["source_count"] == 2
        assert len(data["sources"]) == 2
        assert data["sources"][0]["title"] == "Quantum computing"

    async def it_names_the_artifact_wikipedia_sources(self, a2a_roundtrip):
        tasks = await a2a_roundtrip(
            retriever.CARD, retriever.RetrieverExecutor(), "anything"
        )

        assert tasks[-1].artifacts[0].name == "wikipedia_sources"

    async def it_streams_interim_working_updates(self, a2a_progress_notes):
        # The Retriever declares streaming=True and should emit several `working`
        # status notes (search -> found pages -> retrieved) as it goes. These are
        # captured at receive time, since the final Task only holds the last status.
        notes = await a2a_progress_notes(
            retriever.CARD, retriever.RetrieverExecutor(), "quantum computing"
        )

        assert any("Searching Wikipedia" in n for n in notes), notes
        assert any("Found 2 pages" in n for n in notes), notes
        assert any("Retrieved" in n for n in notes), notes
