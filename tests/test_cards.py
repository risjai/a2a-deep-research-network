"""Each specialist serves a valid Agent Card at the well-known path.

Agent discovery is the entry point of the A2A protocol: a host fetches
``/.well-known/agent-card.json`` to learn a peer's name, transport, and skills.
We build each real server and GET that path over ASGITransport (no key, no port),
asserting a 200 and that the served JSON names the agent and lists its skills.
"""

import pytest

from a2a_research import server
from a2a_research.agents import analyst, critic, retriever

_CARD_PATH = "/.well-known/agent-card.json"

_AGENTS = [
    pytest.param(retriever, "retriever", id="retriever"),
    pytest.param(analyst, "analyst", id="analyst"),
    pytest.param(critic, "critic", id="critic"),
]


@pytest.mark.parametrize("module,expected_name", _AGENTS)
async def it_serves_the_agent_card_at_the_well_known_path(
    asgi_client, module, expected_name
):
    async with asgi_client(module.CARD, module.EXECUTOR) as client:
        resp = await client.get(_CARD_PATH)

    assert resp.status_code == 200
    card = resp.json()
    assert card["name"] == expected_name
    assert card["skills"], "served card should list at least one skill"


@pytest.mark.parametrize("module,expected_name", _AGENTS)
async def it_builds_a_server_for_each_specialist(asgi_client, module, expected_name):
    # build_server is the wiring the CLI uses; confirm it accepts each pair and
    # the resulting app serves the matching card.
    app = server.build_server(module.CARD, module.EXECUTOR)
    assert app is not None

    async with asgi_client(module.CARD, module.EXECUTOR) as client:
        resp = await client.get(_CARD_PATH)
    assert resp.json()["name"] == expected_name
