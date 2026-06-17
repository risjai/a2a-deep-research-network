# Roadmap

Where this project is and where it could go. The guiding principle: **every item
should demonstrate an A2A protocol capability the repo doesn't yet exercise** —
depth over feature-count, since this is a learning/portfolio project.

## Where we are today (v0.1.0)

✅ Three specialist A2A servers (Retriever / Analyst / Critic), each with its own
Agent Card, task lifecycle, and artifacts.
✅ ADK host orchestrator discovering them via Agent Cards and delegating as
`RemoteA2aAgent` sub-agents.
✅ One-command keyless demo + 22-test CI-safe suite + GitHub Actions CI.

**Known gaps (the honest list):**
- All agents declare `capabilities.streaming=False` — streaming is *not* yet shown.
- The full LLM-driven host pipeline is **not integration-tested** and has not been
  run end-to-end with a live key.
- Task states `input-required` and `auth-required` exist in the protocol but are unused.
- No persistence, no auth, no observability surfaced.

---

## Phase 1 — Make the existing system trustworthy (highest priority)

Small, high-value, mostly no new concepts. Do these before adding features.

- [ ] **1.1 Run the full pipeline live and capture it.** Run `python -m a2a_research
  run "..."` with a Gemini key end-to-end; fix whatever the never-run delegation
  path surfaces (esp. how `RemoteA2aAgent` returns artifacts to the host LLM — flagged
  in `ARCHITECTURE.md §10`). Commit a real transcript to the README.
  _Verify: a real report prints; README transcript matches actual output._
- [x] **1.2 Integration-test the host** behind a stubbed/fake model so the
  orchestration logic is covered without a key. _Done: `tests/test_host_orchestrator.py`
  drives `stream_query` with a fake `BaseLlm` (no network) and unit-tests `_event_text`._
- [ ] **1.3 Connection-failure UX.** When a specialist is down, the host/CLI should
  fail with the clear "start the specialists first" message (already drafted in
  `cli.py`) — add a test that asserts it. _Verify: test passes with servers down._

## Phase 2 — Demonstrate streaming (the headline A2A feature still missing)

A2A's task model is built for incremental updates; right now everything is one-shot.

- [ ] **2.1 Stream the Retriever:** flip `streaming=True` and emit a
  `working` status update per source as it resolves (`TaskUpdater.update_status`),
  then the final artifact. _Verify: client sees multiple status events before completion._
- [ ] **2.2 Stream the Analyst/Critic** token-by-token using Gemini's streaming API,
  forwarding chunks as artifact appends (`add_artifact(..., append=True)`).
  _Verify: partial text arrives incrementally over A2A._
- [ ] **2.3 CLI live rendering** of streamed events so the demo visibly "types."

## Phase 3 — Human-in-the-loop & richer protocol surface

- [ ] **3.1 `input-required` flow:** when a research question is ambiguous, the host
  pauses the task in `input-required` and asks the user to clarify, then resumes.
  Exercises the most interesting under-used part of the task lifecycle.
- [ ] **3.2 Multi-part / file artifacts:** have the Analyst return the brief as both a
  human-readable `TextPart` and a structured `DataPart` (sections, citations), and/or
  a `FilePart` (e.g. a Markdown report). _Verify: client can consume both._
- [ ] **3.3 A fourth specialist** in a *different framework* (e.g. a LangGraph or raw
  Starlette agent) to make the polyglot-interop point explicit — the strongest "why
  A2A exists" signal.

## Phase 4 — Production-shaped concerns (only if the project grows)

- [ ] **4.1 Auth:** add a security scheme to the Agent Cards and an API-key/bearer
  check on the servers; exercise the `auth-required` state.
- [ ] **4.2 Persistence:** swap `InMemoryTaskStore` for a SQLite-backed store so tasks
  survive restarts (the SDK ships a DB task store).
- [ ] **4.3 Observability:** wire the already-present OpenTelemetry deps to trace a
  request across host → specialists; export to a local collector.
- [ ] **4.4 Containerize:** a `docker-compose.yml` bringing up all three specialists +
  host with one command.

## Phase 5 — Polish & reach

- [ ] **5.1 Architecture diagram** (Mermaid sequence diagram of the full delegation flow).
- [ ] **5.2 Short demo GIF/asciinema** in the README.
- [ ] **5.3 Blog-style writeup** ("What I learned building on A2A") — doubles as
  interview prep.

---

## Suggested next step

**Phase 1.1 + 1.2.** The single most valuable move is proving the full pipeline
actually works end-to-end and locking it with a test — that closes the one honest
gap in the current repo before building anything new on top of it.
