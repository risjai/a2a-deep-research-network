"""One-command demo of the A2A protocol layer — no API key required.

Starts the three specialist A2A servers as subprocesses, waits for each Agent
Card to be reachable, then acts as an A2A *client*: it discovers the Retriever
by its card and sends a research topic, printing the structured artifact that
comes back over the protocol.

This exercises the full A2A path (discovery -> task lifecycle -> artifact) using
only the Retriever, which needs no LLM, so it runs with zero credentials. To see
the full host-orchestrated pipeline (Analyst + Critic too), set GOOGLE_API_KEY
and run:  python -m a2a_research run "your question"

    uv run python demo.py
    uv run python demo.py "the history of jazz"
"""

import asyncio
import subprocess
import sys

import httpx

from a2a_research import config
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import Message, Part, Role, TextPart

SPECIALISTS = ("retriever", "analyst", "critic")


async def _wait_for_card(client: httpx.AsyncClient, name: str, attempts: int = 30) -> None:
    """Poll a specialist's well-known card URL until it answers (or give up)."""
    url = config.card_url(name)
    for _ in range(attempts):
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                print(f"  ✓ {name:<9} discovered at {url}")
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.3)
    raise RuntimeError(f"{name} did not come up at {url}")


async def _query_retriever(client: httpx.AsyncClient, topic: str) -> dict:
    """Discover the Retriever by its card and send it a topic over A2A."""
    card = await A2ACardResolver(client, base_url=config.base_url("retriever")).get_agent_card()
    a2a_client = ClientFactory(ClientConfig(httpx_client=client, streaming=True)).create(card)
    message = Message(
        role=Role.user, message_id="demo-1", parts=[Part(root=TextPart(text=topic))]
    )
    data: dict = {}
    async for event in a2a_client.send_message(message):
        task = event[0] if isinstance(event, tuple) else event
        update = event[1] if isinstance(event, tuple) and len(event) > 1 else None
        # Print interim `working` status notes as the Retriever streams them.
        status = getattr(update, "status", None)
        status_msg = getattr(status, "message", None)
        if status_msg and status_msg.parts:
            note = "".join(
                p.root.text for p in status_msg.parts if getattr(p.root, "text", None)
            )
            if note:
                print(f"  … {note}")
        if getattr(task, "artifacts", None):
            data = task.artifacts[0].parts[0].root.data
    return data


async def _main(topic: str) -> None:
    print(f"Starting {len(SPECIALISTS)} A2A specialist servers...")
    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "a2a_research", "serve", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for name in SPECIALISTS
    ]
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            for name in SPECIALISTS:
                await _wait_for_card(client, name)

            print(f'\nAsking the Retriever (over A2A): "{topic}"\n')
            data = await _query_retriever(client, topic)

            print(f"Topic: {data.get('topic')}")
            print(f"Sources found: {data.get('source_count')}\n")
            for i, src in enumerate(data.get("sources", []), 1):
                extract = (src.get("extract") or "").strip()
                snippet = extract[:160] + ("…" if len(extract) > 160 else "")
                print(f"{i}. {src.get('title')}\n   {src.get('url')}\n   {snippet}\n")

        print("Done. This used only the no-LLM Retriever — the full A2A path with")
        print("zero credentials. Set GOOGLE_API_KEY and run:")
        print('  python -m a2a_research run "your research question"')
    finally:
        for proc in procs:
            proc.terminate()
        for proc in procs:
            proc.wait()


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "the Apollo program"
    asyncio.run(_main(topic))
