"""Thin Gemini wrapper with graceful degradation.

The Analyst and Critic specialists call :func:`generate`. When no API key is
present the call returns a deterministic *stub* string instead of failing, so the
full A2A round-trip (task lifecycle + artifact emission) is demoable and testable
without any credentials. The key is checked at call time, never at import, so
tests can toggle it.
"""

import os

from .config import MODEL


def has_key() -> bool:
    """True if a Gemini API key is available in the environment."""
    return bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))


async def generate(prompt: str, *, stub_label: str) -> str:
    """Return Gemini's response to ``prompt``, or a deterministic stub if no key."""
    if not has_key():
        return _stub(prompt, stub_label)
    from google import genai

    client = genai.Client()  # reads GOOGLE_API_KEY/GEMINI_API_KEY from env
    resp = await client.aio.models.generate_content(model=MODEL, contents=prompt)
    return resp.text


def _stub(prompt: str, label: str) -> str:
    """A clear, deterministic, labeled placeholder echoing the input shape."""
    head = prompt.strip().splitlines()[0][:200] if prompt.strip() else "(no input)"
    return (
        f"[{label} — stub mode, no GOOGLE_API_KEY set]\n"
        f"Input received ({len(prompt)} chars). First line: {head}\n"
        f"Set GOOGLE_API_KEY to enable live {label}."
    )
