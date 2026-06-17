"""Shared test fixtures.

The centerpiece is :func:`a2a_roundtrip`: an in-process A2A round-trip helper
that wires a card + executor into a real ``A2AStarletteApplication`` and talks to
it over ``httpx.ASGITransport`` — no sockets, no ports, and (crucially) no API
key. This is the proven pattern from ``docs/VERIFIED_API.md``: the streaming
client yields ``(Task, update)`` tuples, so we unwrap the ``Task`` and collect the
terminal states/artifacts the server actually emitted over the wire.
"""

import httpx
import pytest

from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.server.agent_execution import AgentExecutor
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, Message, Part, Role, TextPart

_BASE_URL = "http://test"


def build_asgi_app(card: AgentCard, executor: AgentExecutor):
    """Build the same Starlette ASGI app the real servers serve."""
    handler = DefaultRequestHandler(
        agent_executor=executor, task_store=InMemoryTaskStore()
    )
    return A2AStarletteApplication(agent_card=card, http_handler=handler).build()


@pytest.fixture
def a2a_roundtrip():
    """Return an async helper that runs one in-process A2A message round-trip.

    Usage::

        tasks = await a2a_roundtrip(CARD, EXECUTOR, "the topic")
        final = tasks[-1]
        assert final.status.state == TaskState.completed

    Returns the list of ``Task`` objects emitted by ``send_message`` (each event
    is a ``(Task, update)`` tuple per the verified API; we keep the ``Task``).
    """

    async def _run(card: AgentCard, executor: AgentExecutor, text: str):
        asgi = build_asgi_app(card, executor)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=asgi), base_url=_BASE_URL
        ) as client:
            fetched = await A2ACardResolver(
                client, base_url=_BASE_URL
            ).get_agent_card()
            a2a_client = ClientFactory(
                ClientConfig(httpx_client=client, streaming=True)
            ).create(fetched)
            message = Message(
                role=Role.user,
                message_id="test-message-1",
                parts=[Part(root=TextPart(text=text))],
            )
            tasks = []
            async for event in a2a_client.send_message(message):
                task = event[0] if isinstance(event, tuple) else event
                tasks.append(task)
            return tasks

    return _run


@pytest.fixture
def asgi_client():
    """Return an async helper yielding an httpx client bound to a card+executor app.

    Usage::

        async with asgi_client(CARD, EXECUTOR) as client:
            resp = await client.get("/.well-known/agent-card.json")
    """

    def _make(card: AgentCard, executor: AgentExecutor):
        asgi = build_asgi_app(card, executor)
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=asgi), base_url=_BASE_URL
        )

    return _make
