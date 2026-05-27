"""Redis-backed cache service for embedding and retrieval results."""

from __future__ import annotations

import hashlib
import json
import logging

from rag_mcp.core.settings import RedisSettings
from rag_mcp.infrastructure.redis.client import RedisClient

logger = logging.getLogger(__name__)


def _hash_text(text: str) -> str:
    """Return a deterministic hex digest for cache keying."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class RedisCacheService:
    """Unified cache service backed by Redis."""

    def __init__(self, redis_client: RedisClient, settings: RedisSettings) -> None:
        self._redis = redis_client.client
        self._settings = settings

    # -- Embedding cache -------------------------------------------------------

    def get_embedding(self, text: str) -> list[float] | None:
        """Return cached embedding vector, or None on miss."""
        key = f"rag:emb:{_hash_text(text)}"
        try:
            raw = self._redis.get(key)
        except Exception:
            logger.warning("Redis embedding cache GET failed", exc_info=True)
            return None
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
            return payload["vector"]
        except (json.JSONDecodeError, KeyError):
            logger.warning("Invalid cached embedding data for key %s", key)
            return None

    def set_embedding(self, text: str, vector: list[float], model: str = "") -> None:
        """Cache an embedding vector."""
        key = f"rag:emb:{_hash_text(text)}"
        payload = json.dumps({"vector": vector, "model": model})
        try:
            self._redis.setex(key, self._settings.ttl_embedding, payload)
        except Exception:
            logger.warning("Redis embedding cache SET failed", exc_info=True)

    # -- Batch embedding cache -------------------------------------------------

    def get_embeddings(self, texts: list[str]) -> list[list[float] | None]:
        """Batch fetch cached embeddings. Returns None for cache misses."""
        if not texts:
            return []
        keys = [f"rag:emb:{_hash_text(t)}" for t in texts]
        try:
            pipe = self._redis.pipeline(transaction=False)
            for key in keys:
                pipe.get(key)
            raw_results = pipe.execute()
        except Exception:
            logger.warning("Redis batch embedding cache GET failed", exc_info=True)
            return [None] * len(texts)
        results: list[list[float] | None] = []
        for raw in raw_results:
            if raw is None:
                results.append(None)
            else:
                try:
                    results.append(json.loads(raw)["vector"])
                except (json.JSONDecodeError, KeyError):
                    results.append(None)
        return results

    def set_embeddings(
        self, texts: list[str], vectors: list[list[float]], model: str = ""
    ) -> None:
        """Batch cache embedding vectors."""
        if not texts:
            return
        try:
            pipe = self._redis.pipeline(transaction=False)
            for text, vector in zip(texts, vectors):
                key = f"rag:emb:{_hash_text(text)}"
                pipe.setex(key, self._settings.ttl_embedding, json.dumps({"vector": vector, "model": model}))
            pipe.execute()
        except Exception:
            logger.warning("Redis batch embedding cache SET failed", exc_info=True)

    # -- Retrieval cache -------------------------------------------------------

    def get_retrieval(self, query: str, collection: str) -> list[dict] | None:
        """Return cached retrieval results, or None on miss."""
        composite = f"{collection}:{query}"
        key = f"rag:ret:{_hash_text(composite)}"
        try:
            raw = self._redis.get(key)
        except Exception:
            logger.warning("Redis retrieval cache GET failed", exc_info=True)
            return None
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
            return payload["results"]
        except (json.JSONDecodeError, KeyError):
            logger.warning("Invalid cached retrieval data for key %s", key)
            return None

    def set_retrieval(
        self,
        query: str,
        collection: str,
        results: list[dict],
    ) -> None:
        """Cache retrieval results."""
        composite = f"{collection}:{query}"
        key = f"rag:ret:{_hash_text(composite)}"
        payload = json.dumps({"results": results, "query": query, "collection": collection})
        try:
            self._redis.setex(key, self._settings.ttl_retrieval, payload)
        except Exception:
            logger.warning("Redis retrieval cache SET failed", exc_info=True)
