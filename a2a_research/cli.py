"""Command-line entrypoint.

    python -m a2a_research serve retriever     # start a specialist server
    python -m a2a_research serve analyst
    python -m a2a_research serve critic
    python -m a2a_research run "How does CRISPR gene editing work?"

Start the three specialists (each in its own terminal), then `run` a question
through the ADK host, which discovers them by their Agent Cards and delegates.
"""

import asyncio
import importlib

import click
import uvicorn

from . import config
from .server import build_server

_SPECIALISTS = ("retriever", "analyst", "critic")


@click.group()
def main() -> None:
    """A2A Deep Research Network."""


@main.command()
@click.argument("name", type=click.Choice(_SPECIALISTS))
def serve(name: str) -> None:
    """Run a specialist A2A server (blocking) on its configured port."""
    module = importlib.import_module(f".agents.{name}", package="a2a_research")
    app = build_server(module.CARD, module.EXECUTOR)
    port = config.PORTS[name]
    click.echo(f"Serving '{name}' at {config.base_url(name)} (card at {config.card_url(name)})")
    uvicorn.run(app.build(), host=config.HOST, port=port)


@main.command()
@click.argument("question")
def run(question: str) -> None:
    """Run a research QUESTION through the host orchestrator."""
    from .host.orchestrator import stream_query

    async def _drive() -> None:
        async for author, text, is_final in stream_query(question):
            prefix = "FINAL REPORT" if is_final else f"[{author}]"
            click.echo(f"\n{prefix}\n{text}")

    try:
        asyncio.run(_drive())
    except Exception as exc:  # most often: a specialist server isn't running
        raise SystemExit(
            f"Error: {exc}\n\nMake sure the specialists are running first:\n"
            "  python -m a2a_research serve retriever\n"
            "  python -m a2a_research serve analyst\n"
            "  python -m a2a_research serve critic\n"
            "and that GOOGLE_API_KEY is set (the host uses an LLM)."
        ) from exc


if __name__ == "__main__":
    main()
