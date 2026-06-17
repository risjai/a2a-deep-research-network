# Verified A2A + ADK API Reference

> **Single source of truth for this repo.** Every signature below was captured by
> introspecting the *installed* packages — not from memory or web tutorials (which
> are mostly written against the older pre-0.3 API). Code against THIS file.
>
> Pinned versions: `a2a-sdk==0.3.26`, `google-adk==2.2.0`, Python `>=3.10`.

## Why these exact versions

`google-adk==2.2.0` declares `a2a-sdk<0.4,>=0.3.4`. Its `RemoteA2aAgent` imports
`a2a.client.middleware`, `a2a.client.client.ClientConfig`, etc. — paths that exist in
the 0.3.x line but were removed in the 1.x protobuf rewrite. **a2a-sdk 1.x + ADK 2.2.0
fails at import.** We pin `a2a-sdk==0.3.26` (latest 0.3.x). In 0.3.x, `AgentCard`/
`Message`/`AgentSkill` are clean Pydantic models (base `A2ABaseModel`).

---

## A2A SERVER side (`a2a-sdk`)

### Types — `from a2a.types import ...`

```python
AgentCard(
    name: str, description: str, url: str, version: str,
    capabilities: AgentCapabilities,
    default_input_modes: list[str],      # e.g. ["text/plain"]
    default_output_modes: list[str],     # e.g. ["text/plain"]
    skills: list[AgentSkill],
    # optional: provider, documentation_url, icon_url, preferred_transport,
    #           protocol_version, security, security_schemes, supports_authenticated_extended_card
)

AgentSkill(
    id: str, name: str, description: str, tags: list[str],
    examples: list[str] | None = None,
    input_modes: list[str] | None = None, output_modes: list[str] | None = None,
)

AgentCapabilities(
    streaming: bool | None = None,
    push_notifications: bool | None = None,
    state_transition_history: bool | None = None,
    extensions: list | None = None,
)

# TaskState enum string values:
#   submitted, working, input-required, completed, canceled, failed, rejected, auth-required, unknown

# Parts (Part is a RootModel over a union):
TextPart(text=str)         # kind auto-set to "text"
DataPart(data=dict)        # kind auto-set to "data" — use for STRUCTURED artifacts
# Wrap in Part(root=TextPart(...)) when a list[Part] is required.
```

### AgentExecutor — `from a2a.server.agent_execution import AgentExecutor, RequestContext`

```python
class AgentExecutor(ABC):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None: ...
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None: ...
```

`RequestContext`:
- `context.get_user_input(delimiter="\n") -> str`  ← the user's text
- `context.message`, `context.task_id`, `context.context_id`, `context.current_task` (properties)

### TaskUpdater — `from a2a.server.tasks import TaskUpdater`

```python
TaskUpdater(event_queue: EventQueue, task_id: str, context_id: str)

await updater.submit()          # -> state: submitted
await updater.start_work()      # -> state: working
await updater.complete(message=None)    # -> terminal: completed
await updater.failed(message=None)      # -> terminal: failed
await updater.update_status(state: TaskState, message: Message|None=None, final: bool=False, metadata: dict|None=None)
await updater.add_artifact(parts: list[Part], artifact_id=None, name: str|None=None,
                           metadata: dict|None=None, append=None, last_chunk=None) -> None
msg = updater.new_agent_message(parts: list[Part])   # build a Message to pass to update_status/complete
```

### Message helper — `from a2a.utils import new_agent_text_message`

```python
new_agent_text_message(text: str, context_id: str|None=None, task_id: str|None=None) -> Message
```

### Wiring the HTTP app

```python
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

handler = DefaultRequestHandler(
    agent_executor=MyExecutor(),
    task_store=InMemoryTaskStore(),
)
app = A2AStarletteApplication(agent_card=card, http_handler=handler)
# app.build() -> a Starlette ASGI app. Serve with: uvicorn.run(app.build(), host, port)
# Agent card auto-served at:  /.well-known/agent-card.json
```

---

## A2A CLIENT / HOST side (`google-adk`)

### RemoteA2aAgent — `from google.adk.agents.remote_a2a_agent import RemoteA2aAgent, AGENT_CARD_WELL_KNOWN_PATH`

```python
RemoteA2aAgent(
    name: str,
    agent_card: str | AgentCard,   # a URL string to the card works:
                                   #   f"{base_url}{AGENT_CARD_WELL_KNOWN_PATH}"
    *, description: str = "",
    timeout: float = 600.0,
)
# AGENT_CARD_WELL_KNOWN_PATH == "/.well-known/agent-card.json"
```

**Key fact:** `RemoteA2aAgent` subclasses `BaseAgent`, so on the host it goes in
`LlmAgent(sub_agents=[...])` (LLM-driven delegation/transfer), NOT in `tools=[...]`.

### Host LlmAgent + Runner

```python
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

host = LlmAgent(
    name="host",
    model="gemini-2.0-flash",          # requires GOOGLE_API_KEY (or GEMINI_API_KEY) env var
    instruction="...",
    description="...",
    sub_agents=[remote_retriever, remote_analyst, remote_critic],
)

runner = Runner(agent=host, app_name="...", session_service=InMemorySessionService())
# Runner is keyword-only. Must create a session before running:
#   await session_service.create_session(app_name=..., user_id=..., session_id=...)
# Then iterate:  async for event in runner.run_async(user_id=..., session_id=..., new_message=Content(...)):
# Build new_message with: from google.genai import types; types.Content(role="user", parts=[types.Part(text=...)])
```

### Model / key

- Env var: `GOOGLE_API_KEY` (Gemini API). Model string e.g. `"gemini-2.0-flash"`.
- The Retriever specialist uses NO LLM (pure Wikipedia API), so the A2A protocol layer
  is fully demoable/testable without any API key.

---

## VERIFIED in-process round-trip (no API key, no real port)

This exact pattern was run and passes — use it for tests and as the canonical client usage.
Note: `A2AStarletteApplication` requires the `http-server` extra (`a2a-sdk[http-server]`,
which pulls `sse-starlette`). Client `send_message` yields **tuples** `(Task, update_event)`.

```python
import httpx
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.client import A2ACardResolver, ClientFactory, ClientConfig
from a2a.types import Message, Role, Part, TextPart

asgi = A2AStarletteApplication(card, DefaultRequestHandler(
    agent_executor=MyExecutor(), task_store=InMemoryTaskStore())).build()

async with httpx.AsyncClient(transport=httpx.ASGITransport(app=asgi),
                             base_url="http://test") as client:
    # card is auto-served:
    r = await client.get("/.well-known/agent-card.json")        # -> 200
    fetched = await A2ACardResolver(client, base_url="http://test").get_agent_card()
    c = ClientFactory(ClientConfig(httpx_client=client, streaming=True)).create(fetched)
    msg = Message(role=Role.user, message_id="m1",
                  parts=[Part(root=TextPart(text="hello A2A"))])
    async for event in c.send_message(msg):     # events are tuples: (Task, update|None)
        task = event[0] if isinstance(event, tuple) else event
        if getattr(task, "artifacts", None):
            data = task.artifacts[0].parts[0].root.data     # DataPart payload round-trips
```

## Confirmed import smoke test (passes on this machine)

```python
from google.adk.agents import LlmAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent, AGENT_CARD_WELL_KNOWN_PATH
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCard, AgentSkill, AgentCapabilities, TaskState, Part, TextPart, DataPart
from a2a.utils import new_agent_text_message
```
