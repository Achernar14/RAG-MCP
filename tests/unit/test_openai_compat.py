"""Unit tests for OpenAI-compatible endpoint URL construction.

Covers the URL concatenation convention used by DeepSeekLlmProvider
(and any future OpenAI-compatible LLM provider).
"""

from __future__ import annotations

import pytest


class TestApiBaseUrlConvention:
    """Verify that api_base URLs produce correct chat/completions endpoints.

    The convention: api_base is the provider's root API URL, which
    SHOULD include the ``/v1`` prefix when it is part of the API path
    (e.g. ``https://api.openai.com/v1``).  The provider appends
    ``/chat/completions`` to construct the full endpoint.
    """

    @staticmethod
    def _build_url(api_base: str) -> str:
        """Replicate the URL construction from DeepSeekLlmProvider."""
        cleaned = api_base.rstrip("/")
        return f"{cleaned}/chat/completions"

    # ── Standard provider URLs ──────────────────────────────

    def test_deepseek_default(self):
        url = self._build_url("https://api.deepseek.com")
        assert url == "https://api.deepseek.com/chat/completions"

    def test_openai_standard(self):
        url = self._build_url("https://api.openai.com/v1")
        assert url == "https://api.openai.com/v1/chat/completions"

    # ── Gateway / proxy URLs ───────────────────────────────

    def test_litellm_proxy(self):
        url = self._build_url("http://localhost:4000/v1")
        assert url == "http://localhost:4000/v1/chat/completions"

    def test_synapse_gateway(self):
        url = self._build_url("https://synapse.example.com/v1")
        assert url == "https://synapse.example.com/v1/chat/completions"

    def test_openrouter(self):
        url = self._build_url("https://openrouter.ai/api/v1")
        assert url == "https://openrouter.ai/api/v1/chat/completions"

    # ── Edge cases ─────────────────────────────────────────

    def test_trailing_slash_stripped(self):
        url = self._build_url("https://api.deepseek.com/")
        assert url == "https://api.deepseek.com/chat/completions"

    def test_no_v1_prefix(self):
        """Without /v1 prefix the URL still works — it just appends directly."""
        url = self._build_url("https://custom-llm.example.com")
        assert url == "https://custom-llm.example.com/chat/completions"

    def test_custom_port(self):
        url = self._build_url("http://192.168.1.100:8080/v1")
        assert url == "http://192.168.1.100:8080/v1/chat/completions"

    # ── Documentation tests (guarantee) ────────────────────

    def test_openai_gateway_requires_v1(self):
        """If the gateway's API base omits /v1, the resulting URL is WRONG
        for OpenAI's endpoint convention (should be /v1/chat/completions)."""
        url_without_v1 = self._build_url("https://api.openai.com")
        assert url_without_v1 == "https://api.openai.com/chat/completions"
        # This is NOT the correct OpenAI endpoint; the correct one includes /v1.
        assert url_without_v1 != "https://api.openai.com/v1/chat/completions"
