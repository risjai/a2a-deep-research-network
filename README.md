# A2A Deep Research Network

A small **multi-agent research system** that demonstrates Google's
[**Agent2Agent (A2A) protocol**](https://a2a-protocol.org) end to end. A host
orchestrator (built with the **Google Agent Development Kit, ADK**) discovers three
independent specialist agents through their **Agent Cards** and delegates a research
question to them over A2A:

```
                 ┌─────────────────────────────┐
   "Research X"  │   Host Orchestrator (ADK)   │
  ───────────────▶  LlmAgent + RemoteA2aAgent  │
                 └──────┬───────┬───────┬───────┘
                        │  A2A  │  A2A  │  A2A      (JSON-RPC over HTTP,
              ┌─────────▼┐ ┌────▼─────┐ ┌▼─────────┐  Agent Cards at
              │ Retriever│ │ Analyst  │ │  Critic  │  /.well-known/…)
              │ (no LLM, │ │ (Gemini) │ │ (Gemini) │
              │ Wikipedia)│ └──────────┘ └──────────┘
              └──────────┘
```

Each specialist is a **standalone A2A server** — its own process, its own Agent Card,
its own task lifecycle (`submitted → working → completed`) and structured **artifacts**.
The host never imports their code; it talks to them purely over the protocol.

## Why this is more than a toy

A single-agent "call two APIs" demo doesn't exercise what A2A is *for*. This project shows:

- **Discovery** via Agent Cards (`/.well-known/agent-card.json`)
- **Cross-process delegation** — the host orchestrates agents it has no code dependency on
- **The full task lifecycle** — state transitions, streaming status updates, artifacts
- **Graceful degradation** — the Retriever needs **no API key** (Wikipedia REST API), so
  the entire A2A protocol layer is demoable and CI-testable without credentials.

## What's here

| Component | Stack | Needs a key? | Role |
|-----------|-------|--------------|------|
| Retriever agent | a2a-sdk server + Wikipedia REST | ❌ | Gathers source material on the topic |
| Analyst agent | a2a-sdk server + Gemini | ✅ (degrades) | Synthesizes findings into a brief |
| Critic agent | a2a-sdk server + Gemini | ✅ (degrades) | Fact-checks and surfaces gaps |
| Host orchestrator | google-adk `LlmAgent` | ✅ | Decomposes the question, delegates, composes the report |

> **Versions are pinned deliberately:** `a2a-sdk==0.3.26`, `google-adk==2.2.0`.
> See [`docs/VERIFIED_API.md`](docs/VERIFIED_API.md) for the exact, introspected API
> surface and *why* these versions (1.x of a2a-sdk is incompatible with ADK 2.2.0).

## Quickstart

```bash
uv sync
# (optional) export GOOGLE_API_KEY=...   # only needed for Analyst/Critic/host LLM calls
```

_Run instructions land as the agents are built — see commit history for the build story._

## Project status

Built iteratively; the git history is intentionally commit-by-commit to show the
architecture coming together one verifiable slice at a time.
