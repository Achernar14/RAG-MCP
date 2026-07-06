"""OpenAI-compatible chat completion provider.

This is a generic provider that works with any OpenAI-compatible API
(DeepSeek, OpenAI, LiteLLM proxy, Synapse, OpenRouter, etc.).
"""

from __future__ import annotations

import httpx

from rag_mcp.core.exceptions import ProviderError
from rag_mcp.infrastructure.providers.utils import require_env_value


class OpenAICompatibleLlmProvider:
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

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Generate a grounded completion."""
        url = f"{self.api_base}/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
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
