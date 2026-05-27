"""Caching wrapper for embedding providers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rag_mcp.infrastructure.redis.cache import RedisCacheService

logger = logging.getLogger(__name__)


class CachingEmbeddingProvider:
    """Wraps an embedding provider with Redis caching.

    For each text, checks the Redis cache first.  On a miss the delegate
    provider is called and the result is stored in Redis.
    """

    def __init__(self, delegate, cache: RedisCacheService) -> None:
        self._delegate = delegate
        self._cache = cache

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings, using cache when available."""
        if not texts:
            return []

        cached = self._cache.get_embeddings(texts)
        miss_indices = [i for i, c in enumerate(cached) if c is None]

        if not miss_indices:
            return cached  # type: ignore[return-value]

        miss_texts = [texts[i] for i in miss_indices]
        fresh_vectors = self._delegate.embed_texts(miss_texts)
        self._cache.set_embeddings(miss_texts, fresh_vectors)

        results: list[list[float]] = list(cached)  # type: ignore[arg-type]
        for idx, vec in zip(miss_indices, fresh_vectors):
            results[idx] = vec
        return results
