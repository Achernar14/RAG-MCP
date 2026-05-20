"""Zhipu embedding provider."""

from __future__ import annotations

import httpx

from rag_mcp.core.exceptions import ProviderError
from rag_mcp.infrastructure.providers.utils import require_env_value


class ZhipuEmbeddingProvider:
    """Call Zhipu embedding API over HTTP."""

    def __init__(
        self,
        *,
        api_base: str | None,
        api_key_env: str | None,
        model: str | None,
        timeout_seconds: float,
    ) -> None:
        self.api_base = (api_base or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        self.api_key = require_env_value(api_key_env, provider_name="zhipu embedding")
        self.model = model or "embedding-3"
        self.timeout_seconds = timeout_seconds

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for a list of texts."""
        embeddings: list[list[float]] = []
        for text in texts:
            embeddings.append(self._embed_single(text))
        return embeddings

    def _embed_single(self, text: str) -> list[float]:
        url = f"{self.api_base}/embeddings"
        payload = {"model": self.model, "input": text}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            response = httpx.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception as exc:
            raise ProviderError(f"Zhipu embedding request failed: {exc}") from exc
