"""OpenAI-compatible chat completion provider.

This is a generic provider that works with any OpenAI-compatible API
(DeepSeek, OpenAI, LiteLLM proxy, Synapse, OpenRouter, etc.).
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from rag_mcp.core.exceptions import ProviderError
from rag_mcp.domain.repositories.contracts import LlmProvider
from rag_mcp.infrastructure.providers.utils import require_env_value


class OpenAICompatibleLlmProvider(LlmProvider):
    """Call an OpenAI-compatible chat completions API.

    Works with any provider that exposes a ``/chat/completions`` endpoint
    (OpenAI, DeepSeek, LiteLLM, Synapse, OpenRouter, local vLLM, etc.).
    """

    def __init__(
        self,
        *,
        api_base: str | None,
        api_key_env: str | None,
        model: str | None,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
    ) -> None:
        self.api_base = (api_base or "https://api.deepseek.com").rstrip("/")
        self.api_key = require_env_value(api_key_env, provider_name="openai-compatible llm")
        self.model = model or "deepseek-chat"
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds

    # ── message builder (shared by generate / generate_stream) ──────────

    def _build_messages(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> list[dict[str, str]]:
        """Build the messages list for a chat completion request."""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _build_payload(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
    ) -> dict:
        """Build the JSON payload for a chat completion request."""
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if stream:
            payload["stream"] = True
        return payload

    # ── synchronous generation ──────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Generate a grounded completion."""
        url = f"{self.api_base}/chat/completions"
        messages = self._build_messages(prompt, system_prompt)
        payload = self._build_payload(messages, stream=False)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = httpx.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            raise ProviderError(f"OpenAI-compatible generation request failed: {exc}") from exc

    # ── streaming generation ────────────────────────────────────────────

    def generate_stream(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        metadata: dict | None = None,
    ) -> Iterator[str]:
        """Stream completion tokens from the API via SSE.

        Yields individual delta text chunks as they arrive from the
        upstream provider.  The caller is expected to wrap these chunks
        in SSE ``data:`` frames or equivalent transport.
        """
        url = f"{self.api_base}/chat/completions"
        messages = self._build_messages(prompt, system_prompt)
        payload = self._build_payload(messages, stream=True)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.stream(
                "POST",
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    delta = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    if delta:
                        yield delta
        except Exception as exc:
            raise ProviderError(
                f"OpenAI-compatible streaming request failed: {exc}"
            ) from exc
