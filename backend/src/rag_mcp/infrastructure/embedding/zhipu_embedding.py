"""Zhipu embedding provider."""

from __future__ import annotations

import httpx

from rag_mcp.core.exceptions import ProviderError
from rag_mcp.domain.repositories.contracts import EmbeddingProvider
from rag_mcp.infrastructure.providers.utils import require_env_value


class ZhipuEmbeddingProvider(EmbeddingProvider):
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

    _BATCH_SIZE = 64

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for a list of texts — batch API, one POST per batch."""
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self._BATCH_SIZE):
            batch = texts[i : i + self._BATCH_SIZE]
            all_embeddings.extend(self._embed_batch(batch))
        return all_embeddings

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Send a batch of texts to the Zhipu embedding API in a single request."""
        url = f"{self.api_base}/embeddings"
        payload = {"model": self.model, "input": texts}
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
            items = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in items]
        except Exception as exc:
            raise ProviderError(f"Zhipu embedding request failed: {exc}") from exc
