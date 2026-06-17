"""Graceful-degradation tests for the Gemini wrapper.

With no API key in the environment, ``has_key()`` must be False and ``generate``
must return a deterministic, labeled stub string — never touching the network.
This is what makes the whole suite CI-safe: the Analyst/Critic can complete a
real A2A round-trip with no credentials.
"""

import pytest

from a2a_research import gemini


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    """Ensure no Gemini key is visible for these tests."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


class TestHasKey:
    def it_is_false_when_no_key_is_set(self):
        assert gemini.has_key() is False

    def it_is_true_when_google_api_key_is_set(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
        assert gemini.has_key() is True

    def it_is_true_when_gemini_api_key_is_set(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        assert gemini.has_key() is True


class TestGenerateStubMode:
    async def it_returns_a_stub_string_naming_the_label(self):
        result = await gemini.generate("some prompt", stub_label="analysis")

        assert isinstance(result, str)
        assert "stub mode" in result
        assert "analysis" in result

    async def it_is_deterministic_across_calls(self):
        first = await gemini.generate("some prompt", stub_label="analysis")
        second = await gemini.generate("some prompt", stub_label="analysis")

        assert first == second

    async def it_echoes_the_first_line_of_the_prompt(self):
        result = await gemini.generate(
            "First line here\nSecond line ignored", stub_label="critique"
        )

        assert "First line here" in result
        assert "critique" in result
