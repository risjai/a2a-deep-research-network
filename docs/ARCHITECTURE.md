# A2A Deep Research Network — Implementation Blueprint

> Implementation contract for coding agents. Every API element traces to `docs/VERIFIED_API.md` (introspected from the installed `a2a-sdk==0.3.26` / `google-adk==2.2.0`). Anything not pinned there is in the **VERIFY** list (§10) and must be smoke-tested before being relied on. Do not code against web tutorials — they target the pre-0.3 API and are wrong.

## 0. Verification deltas (read first)

Three load-bearing facts re-introspected from the installed packages:

- **Well-known path is consistent.** `a2a.utils.constants.AGENT_CARD_WELL_KNOWN_PATH == "/.well-known/agent-card.json"` (server side) and ADK imports the same constant. `A2AStarletteApplication.build()` defaults `agent_card_url=AGENT_CARD_WELL_KNOWN_PATH`, `rpc_url="/"`. So the host builds card URLs as `f"{base_url}{AGENT_CARD_WELL_KNOWN_PATH}"`.
- **TaskUpdater method names** (confirmed in `a2a/server/tasks/task_updater.py`): `submit()`, `start_work()` (NOT `working()`), `add_artifact(parts, ...)`, `complete(message=None)`, `failed(message=None)`, `update_status(state, message=None, final=False, ...)`, `new_agent_message(parts, metadata=None)`.
- **Gemini SDK is present transitively.** `google.genai.Client(api_key=...)` exists with async `client.aio.models.generate_content(model=..., contents=...)`. Analyst/Critic call Gemini through this directly — they are A2A servers, NOT ADK agents, so they must not import ADK.

`RequestContext.get_user_input(delimiter="\n")` returns the joined user text or `""`, and `context.task_id` / `context.context_id` are populated by the request handler before `execute()` runs.

---

## 1. File / package tree

**Decision: flat package `a2a_research/` (no `src/`).** Single deployable package, run via `python -m a2a_research`; a `src/` layout adds packaging indirection that buys nothing here.

```
a2a/
├── pyproject.toml                     # exists; add [project.scripts] + pytest dev dep
├── README.md                          # exists; fill run guide last (task #6)
├── docs/
│   ├── VERIFIED_API.md                # exists — source of truth
│   └── ARCHITECTURE.md                # this document
├── a2a_research/
│   ├── __init__.py
│   ├── __main__.py                    # delegates to cli.main()
│   ├── cli.py                         # click group: serve / run
│   ├── config.py                      # PORTS map, host/base-URL helpers, MODEL const
│   ├── executor_base.py               # ResearchExecutor base class (§2)
│   ├── gemini.py                      # thin Gemini wrapper + key detection (§5)
│   ├── server.py                      # build_server(card, executor) -> A2AStarletteApplication
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── retriever.py               # card + RetrieverExecutor + Wikipedia client
│   │   ├── analyst.py                 # card + AnalystExecutor (Gemini, degrades)
│   │   └── critic.py                  # card + CriticExecutor (Gemini, degrades)
│   └── host/
│       ├── __init__.py
│       └── orchestrator.py            # build_host() -> LlmAgent w/ 3 RemoteA2aAgent sub_agents; run_query()
└── tests/
    ├── __init__.py
    ├── conftest.py                    # shared fixtures: httpx ASGITransport client per server
    ├── test_executor_base.py          # lifecycle ordering w/ a fake EventQueue
    ├── test_retriever.py              # Wikipedia client (mocked httpx) + executor artifact shape
    ├── test_analyst_critic.py         # stub-mode determinism (no key) + executor lifecycle
    ├── test_cards.py                  # each card served at /.well-known/agent-card.json
    └── test_e2e_protocol.py           # in-process A2A round-trip, no LLM (retriever only)
```

Tests live in top-level `tests/` (pytest default discovery; no key required for the CI-relevant ones).

---

## 2. Shared executor base — `a2a_research/executor_base.py`

A small abstract base that owns the `submit → start_work → add_artifact → complete` / `failed()` lifecycle so the three specialists implement only their domain logic.

```python
from abc import ABC, abstractmethod
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TextPart

class ResearchExecutor(AgentExecutor, ABC):
    """Wraps the A2A task lifecycle. Subclasses implement run()."""

    # subclass sets this; used as the emitted artifact's `name`
    artifact_name: str = "result"

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.submit()        # -> submitted
        await updater.start_work()    # -> working
        try:
            user_input = context.get_user_input()
            parts = await self.run(user_input, context)   # list[Part]
            await updater.add_artifact(parts, name=self.artifact_name)
            await updater.complete()  # -> completed
        except Exception as exc:
            msg = updater.new_agent_message([Part(root=TextPart(text=f"{type(exc).__name__}: {exc}"))])
            await updater.failed(message=msg)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()

    @abstractmethod
    async def run(self, user_input: str, context: RequestContext) -> list[Part]:
        """Return the artifact parts. Raise on failure -> base marks task failed."""
```

`Part` is a RootModel union, so every part is wrapped `Part(root=TextPart(...))` / `Part(root=DataPart(...))`. This is the only place the lifecycle is spelled out; specialists never call `TaskUpdater` directly.

---

## 3. Per-module responsibilities

### 3a. `server.py` — shared HTTP wiring

```python
def build_server(card: AgentCard, executor: AgentExecutor) -> A2AStarletteApplication:
    handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore())
    return A2AStarletteApplication(agent_card=card, http_handler=handler)
```
Served via `uvicorn.run(app.build(), host="127.0.0.1", port=...)`. Card auto-served at `/.well-known/agent-card.json`; JSON-RPC at `/`.

### 3b. Retriever — `agents/retriever.py` (NO LLM, no key)

- **AgentCard:** `name="retriever"`, `description="Gathers source material on a topic from Wikipedia."`, `version="0.1.0"`, `capabilities=AgentCapabilities(streaming=False)`, `default_input_modes=["text/plain"]`, `default_output_modes=["application/json"]`, `skills=[AgentSkill(id="wikipedia_lookup", name="Wikipedia lookup", description="Search Wikipedia and return summaries for a topic.", tags=["research","wikipedia"], examples=["quantum computing", "the French Revolution"])]`.
- **Input:** `context.get_user_input()` → the topic string.
- **Wikipedia client (httpx, async):**
  1. Search: `GET https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json` → take top N (default 3) `title`s from `data["query"]["search"]`.
  2. For each title: `GET https://en.wikipedia.org/api/rest_v1/page/summary/{title}` → collect `title`, `extract`, `content_urls.desktop.page` (guard missing keys). Set a `User-Agent` header (`"a2a-research/0.1 (demo)"`).
- **Artifact — structured `DataPart`:** one `Part(root=DataPart(data={"topic": ..., "sources": [{"title","extract","url"}], "source_count": n}))`. `artifact_name = "wikipedia_sources"`.
- **Lifecycle:** entirely via `ResearchExecutor` base. Empty/zero-result topic → return a `DataPart` with `sources: []` and `source_count: 0` (a valid empty result, not a failure). Network/HTTP error → raise, base marks `failed`.

### 3c. Analyst — `agents/analyst.py` (Gemini, degrades)

- **AgentCard:** `name="analyst"`, `description="Synthesizes retrieved source material into a concise research brief."`, `default_output_modes=["text/plain"]`, `skills=[AgentSkill(id="synthesize", name="Synthesize brief", description="Turn raw sources into a structured brief.", tags=["analysis","synthesis"])]`.
- **Input:** `context.get_user_input()` → the topic plus whatever source text the host forwards.
- **Logic:** call `gemini.generate(prompt)` from `gemini.py` (§5). Prompt = instruction to produce a 3–5 bullet brief from the provided material.
- **Artifact:** single `Part(root=TextPart(text=brief))`. `artifact_name = "brief"`.
- **Lifecycle:** via base. Missing key → `gemini.generate` returns the deterministic stub string (§5); still a normal `complete()`.

### 3d. Critic — `agents/critic.py` (Gemini, degrades)

- **AgentCard:** `name="critic"`, `description="Fact-checks a brief and surfaces gaps, caveats, and unsupported claims."`, `default_output_modes=["text/plain"]`, `skills=[AgentSkill(id="critique", name="Critique brief", description="Identify gaps and weak claims in a research brief.", tags=["review","fact-check"])]`.
- **Input:** topic + brief text forwarded by host.
- **Logic / artifact / lifecycle:** identical pattern to Analyst, different prompt ("list gaps, caveats, and claims needing a citation"). `artifact_name = "critique"`.

---

## 4. Port map & card URLs — `a2a_research/config.py`

```python
HOST = "127.0.0.1"
PORTS = {"retriever": 8001, "analyst": 8002, "critic": 8003}
MODEL = "gemini-2.0-flash"

def base_url(name: str) -> str:
    return f"http://{HOST}:{PORTS[name]}"

def card_url(name: str) -> str:
    from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH  # "/.well-known/agent-card.json"
    return f"{base_url(name)}{AGENT_CARD_WELL_KNOWN_PATH}"
```

The `AgentCard.url` field for each specialist is set to `base_url(name) + "/"` (the RPC endpoint). The host constructs each `RemoteA2aAgent(agent_card=card_url(name))`.

---

## 5. Graceful degradation — `a2a_research/gemini.py`

```python
import os
def has_key() -> bool:
    return bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))

async def generate(prompt: str, *, stub_label: str) -> str:
    if not has_key():
        return _stub(prompt, stub_label)
    from google import genai
    client = genai.Client()  # reads GOOGLE_API_KEY/GEMINI_API_KEY from env
    resp = await client.aio.models.generate_content(model=MODEL, contents=prompt)
    return resp.text

def _stub(prompt: str, label: str) -> str:
    head = prompt.strip().splitlines()[0][:200] if prompt.strip() else "(no input)"
    return (f"[{label} — stub mode, no GOOGLE_API_KEY set]\n"
            f"Input received ({len(prompt)} chars). First line: {head}\n"
            f"Set GOOGLE_API_KEY to enable live {label}.")
```

- **Detection:** presence of `GOOGLE_API_KEY` or `GEMINI_API_KEY`. Checked at call time (not import) so tests can toggle it.
- **Stub return:** a clear, deterministic, labeled string that echoes input size and first line — proves the A2A round-trip and artifact emission work without a key, and is assert-able in tests.

---

## 6. CLI surface — `a2a_research/cli.py` (click)

```
python -m a2a_research serve retriever        # blocking uvicorn on :8001
python -m a2a_research serve analyst          # :8002
python -m a2a_research serve critic           # :8003
python -m a2a_research run "How does CRISPR gene editing work?"
```

- `serve NAME` — `NAME ∈ {retriever, analyst, critic}` (click.Choice). Looks up `(card, executor)`, calls `uvicorn.run(build_server(card, executor).build(), host=HOST, port=PORTS[name])`.
- `run QUESTION` — async: builds the host, creates an `InMemorySessionService` session, drives `Runner.run_async(...)`, prints streamed events and the final report. Requires the three `serve` processes running; unreachable card URL → clear "start the specialists first" message.
- `[project.scripts]` add: `a2a-research = "a2a_research.cli:main"`.

---

## 7. Host orchestrator — `a2a_research/host/orchestrator.py`

```python
def build_host() -> LlmAgent:
    return LlmAgent(
        name="host",
        model=MODEL,
        description="Research orchestrator that delegates to specialist A2A agents.",
        instruction=(
            "You coordinate a research task. Steps: (1) transfer to `retriever` with the "
            "topic to gather Wikipedia sources; (2) transfer to `analyst` with the topic and "
            "the gathered sources to get a brief; (3) transfer to `critic` with the brief to "
            "find gaps; (4) compose a final report combining the brief and the critique. "
            "Always delegate via your sub-agents; do not invent sources."
        ),
        sub_agents=[
            RemoteA2aAgent(name="retriever", agent_card=card_url("retriever")),
            RemoteA2aAgent(name="analyst",   agent_card=card_url("analyst")),
            RemoteA2aAgent(name="critic",    agent_card=card_url("critic")),
        ],
    )

async def run_query(question: str) -> str: ...   # session + Runner.run_async loop, returns final text
```

`RemoteA2aAgent` subclasses `BaseAgent` → goes in `sub_agents=[...]` (LLM-driven transfer), **never** `tools=[...]`. Host requires `GOOGLE_API_KEY`. Build `new_message` with `from google.genai import types; types.Content(role="user", parts=[types.Part(text=question)])`.

---

## 8. Build / commit sequence

Implement bottom-up; each commit independently verifiable. Maps to tasks #2–#6.

1. **`scaffold`** — package dirs, `__init__.py`s, `config.py`, `server.py`. Verify: `python -c "import a2a_research"` and the VERIFIED_API import smoke test pass.
2. **`executor-base`** — `executor_base.py` + `test_executor_base.py` (assert event ordering submitted→working→artifact→completed, and failed-on-raise).
3. **`retriever`** — `agents/retriever.py` + `test_retriever.py` (mock httpx; assert `DataPart` shape and empty-result handling). No key needed.
4. **`retriever-serve + e2e-protocol`** — wire `serve retriever` in CLI; `test_e2e_protocol.py` in-process A2A round-trip against the retriever only — CI-safe proof the protocol works.
5. **`gemini + analyst + critic`** — `gemini.py`, `agents/analyst.py`, `agents/critic.py` + `test_analyst_critic.py`.
6. **`host + cli-run`** — `host/orchestrator.py`, finish `cli.py run`. Manual smoke (needs key).
7. **`polish`** — README run guide, `[project.scripts]`, pytest dev deps, final review.

---

## 9. Critical details

- **Error handling:** all domain failures raise inside `run()`; the base converts to `updater.failed(message=...)`. Retriever treats zero search hits as a valid empty artifact. Host `run_query` catches connection errors to the card URLs.
- **State management:** `InMemoryTaskStore` per server; `InMemorySessionService` on host; session created via `await session_service.create_session(...)` before `run_async`.
- **Parts discipline:** Retriever → `DataPart`. Analyst/Critic → `TextPart`. Always wrap in `Part(root=...)`.
- **Testing:** CI-meaningful suite runs with **no API key**. Use `pytest-asyncio`; for in-process A2A round-trips prefer `httpx.ASGITransport` against `app.build()`.
- **Security:** no secrets in code; key strictly from env. Wikipedia calls are unauthenticated GETs with a descriptive `User-Agent`. Bind servers to `127.0.0.1` only.

---

## 10. Open questions / VERIFY list

Not fully pinned by `VERIFIED_API.md`; smoke-test before relying on:

1. **Gemini async call shape** — VERIFY `client.aio.models.generate_content(model="gemini-2.0-flash", contents=prompt)` returns an object with `.text`, or fall back to `response.candidates[0].content.parts[0].text`.
2. **How `RemoteA2aAgent` surfaces sub-agent artifacts to the host LLM** — smoke-test the retriever→host path early; if `DataPart` doesn't surface cleanly, also emit a human-readable `TextPart` alongside.
3. **`Runner.run_async` final-event extraction** — VERIFY which event marks the final report (likely last event with `event.content.parts[*].text` / `is_final_response()`).
4. **`AgentCard.url` value** — set to `base_url(name) + "/"`. VERIFY `A2ACardResolver` accepts it.
5. **Specialists are ADK-free** — confirmed: pure a2a-sdk servers calling `google.genai` directly. Do not import `google.adk` in specialist modules.
6. **`uvicorn.run(app.build())`** — confirm it accepts the built Starlette app object directly (run without reload).
