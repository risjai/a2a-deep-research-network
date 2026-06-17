"""Shared configuration: where each specialist agent lives and which model to use.

Keeping ports and URL construction in one place means the host and the servers
agree on addresses without hard-coding strings in multiple modules.
"""

from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH

HOST = "127.0.0.1"

# One fixed localhost port per specialist. Each runs as its own process.
PORTS = {
    "retriever": 8001,
    "analyst": 8002,
    "critic": 8003,
}

# Gemini model used by the Analyst, Critic, and the ADK host. Requires
# GOOGLE_API_KEY (or GEMINI_API_KEY) in the environment.
MODEL = "gemini-2.0-flash"


def base_url(name: str) -> str:
    """The RPC base URL of a specialist (e.g. http://127.0.0.1:8001)."""
    return f"http://{HOST}:{PORTS[name]}"


def card_url(name: str) -> str:
    """The well-known Agent Card URL the host uses to discover a specialist."""
    return f"{base_url(name)}{AGENT_CARD_WELL_KNOWN_PATH}"
