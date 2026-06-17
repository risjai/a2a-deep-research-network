# A2A Deep Research Network

[![tests](https://github.com/risjai/a2a-deep-research-network/actions/workflows/ci.yml/badge.svg)](https://github.com/risjai/a2a-deep-research-network/actions/workflows/ci.yml)

A multi-agent **Deep Research Network** that demonstrates Google's
[**Agent2Agent (A2A) protocol**](https://a2a-protocol.org) end to end. A host
orchestrator built with the **Google Agent Development Kit (ADK)** discovers three
independent specialist agents through their **Agent Cards** and delegates a research
question to them over A2A — then composes a final report.

```
                 ┌─────────────────────────────┐
   "Research X"  │   Host Orchestrator (ADK)   │
  ───────────────▶  LlmAgent + RemoteA2aAgent  │
                 └──────┬───────┬───────┬───────┘
                        │  A2A  │  A2A  │  A2A      JSON-RPC over HTTP;
              ┌─────────▼┐ ┌────▼─────┐ ┌▼─────────┐ each agent's card at
              │ Retriever│ │ Analyst  │ │  Critic  │ /.well-known/agent-card.json
              │ (no LLM, │ │ (Gemini) │ │ (Gemini) │
              │ Wikipedia)│ └──────────┘ └──────────┘
              └──────────┘
```

Each specialist is a **standalone A2A server** — its own process, its own Agent Card,
its own task lifecycle (`submitted → working → completed`) and structured **artifacts**.
The host never imports their code; it talks to them purely over the protocol, exactly
as agents from different teams or vendors would interoperate in the real world.

## What this demonstrates (the A2A concepts)

| Concept | Where it shows up |
|---------|-------------------|
| **Agent discovery** | Host fetches each specialist's Agent Card from `/.well-known/agent-card.json` |
| **Agent Cards** | `name`, `description`, `skills`, `capabilities` declared per agent (`agents/*.py`) |
| **A2A server** | `A2AStarletteApplication` + `AgentExecutor` per specialist (`server.py`, `executor_base.py`) |
| **A2A client / delegation** | ADK `RemoteA2aAgent` wired as **sub-agents** of the host (`host/orchestrator.py`) |
| **Task lifecycle** | `submit → start_work → add_artifact → complete` / `failed` (`executor_base.py`) |
| **Structured artifacts** | Retriever returns a `DataPart`; Analyst/Critic return `TextPart` |
| **Framework interop** | The host (ADK) orchestrates agents that are plain `a2a-sdk` servers — no shared code |

## Quickstart — zero credentials

The Retriever agent uses **no LLM** (just Wikipedia's free API), so the entire A2A
protocol layer runs and is testable **without any API key**:

```bash
uv sync
uv run python demo.py "the history of jazz"
```

The demo launches the three A2A servers, discovers them by their Agent Cards, and sends
a topic to the Retriever over A2A — printing the structured sources it returns:

```
Starting 3 A2A specialist servers...
  ✓ retriever discovered at http://127.0.0.1:8001/.well-known/agent-card.json
  ✓ analyst   discovered at http://127.0.0.1:8002/.well-known/agent-card.json
  ✓ critic    discovered at http://127.0.0.1:8003/.well-known/agent-card.json

Asking the Retriever (over A2A): "the history of jazz"

Topic: the history of jazz
Sources found: 3
1. Jazz
   https://en.wikipedia.org/wiki/Jazz
   Jazz is a music genre that originated in the African-American communities of New Orleans…
...
```

Run the test suite (also no key needed):

```bash
uv run pytest          # 22 tests proving the A2A layer end to end
```

## Full pipeline — with a Gemini key

The Analyst, Critic, and host orchestrator use Gemini. Without a key they degrade to a
clear stub so the A2A flow still works; with a key you get the real research report.

```bash
export GOOGLE_API_KEY=...          # https://aistudio.google.com/apikey (free tier)

# In three separate terminals, start the specialists:
uv run python -m a2a_research serve retriever      # :8001
uv run python -m a2a_research serve analyst        # :8002
uv run python -m a2a_research serve critic         # :8003

# Then drive a research question through the ADK host:
uv run python -m a2a_research run "How does CRISPR gene editing work?"
```

The host is designed to decompose the question, transfer to the Retriever (sources) →
Analyst (brief) → Critic (gaps), and compose a final report, streaming each agent's
contribution as it arrives. (The no-key Retriever path is verified end to end by the
demo and tests; the full LLM-driven orchestration requires a Gemini key to exercise.)

## Project layout

```
a2a_research/
├── config.py            # ports + Agent Card URL construction
├── server.py            # build_server(): card + executor -> A2AStarletteApplication
├── executor_base.py     # ResearchExecutor: owns the A2A task lifecycle
├── gemini.py            # Gemini wrapper with graceful no-key degradation
├── agents/
│   ├── retriever.py     # no-LLM Wikipedia agent -> DataPart artifact
│   ├── analyst.py       # Gemini: synthesize a brief
│   └── critic.py        # Gemini: find gaps and weak claims
├── host/orchestrator.py # ADK LlmAgent discovering the 3 specialists as sub-agents
└── cli.py               # `serve <name>` and `run "<question>"`
tests/                   # CI-safe pytest suite (no API key)
docs/
├── ARCHITECTURE.md      # implementation blueprint
├── ROADMAP.md           # where the project is and where it could go
└── VERIFIED_API.md      # exact, introspected a2a-sdk / ADK API used here
```

## Notes

- **Pinned versions are deliberate:** `a2a-sdk[http-server]==0.3.26`, `google-adk==2.2.0`.
  ADK 2.2.0 requires `a2a-sdk<0.4`, and a2a-sdk 1.x is a protobuf rewrite that breaks
  ADK's `RemoteA2aAgent`. See [`docs/VERIFIED_API.md`](docs/VERIFIED_API.md).
- ADK prints an `[EXPERIMENTAL] RemoteA2aAgent` warning — that flags ADK's *A2A support
  layer* as still maturing; the A2A protocol itself is stable.
- This repo was built commit-by-commit; the git history shows the architecture coming
  together one verifiable slice at a time.

## License

MIT — see [LICENSE](LICENSE).
