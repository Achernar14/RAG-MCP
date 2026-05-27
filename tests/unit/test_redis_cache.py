"""Tests for Redis cache infrastructure."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from rag_mcp.core.settings import RedisCacheSettings, RedisSettings, Settings
from rag_mcp.infrastructure.redis.cache import RedisCacheService, _hash_text


class TestRedisSettings:
    """Verify Redis settings integrate into the Settings model."""

    def test_default_redis_disabled(self):
        settings = Settings()
        assert settings.redis.enabled is False
        assert settings.redis.host == "127.0.0.1"
        assert settings.redis.port == 6379
        assert settings.redis.cache.embedding_enabled is False
        assert settings.redis.cache.retrieval_enabled is False

    def test_redis_settings_from_dict(self):
        raw = {
            "redis": {
                "enabled": True,
                "host": "10.0.0.1",
                "port": 6380,
                "cache": {"embedding_enabled": True, "retrieval_enabled": True},
            }
        }
        settings = Settings.model_validate(raw)
        assert settings.redis.enabled is True
        assert settings.redis.host == "10.0.0.1"
        assert settings.redis.port == 6380
        assert settings.redis.cache.embedding_enabled is True
        assert settings.redis.cache.retrieval_enabled is True

    def test_redis_defaults_are_safe(self):
        """When redis section is omitted entirely, defaults must not break loading."""
        settings = Settings.model_validate({})
        assert settings.redis.enabled is False


class TestHashText:
    """Verify cache key hashing is deterministic."""

    def test_deterministic(self):
        assert _hash_text("hello") == _hash_text("hello")

    def test_different_inputs_different_hashes(self):
        assert _hash_text("hello") != _hash_text("world")


class TestRedisCacheService:
    """Unit tests for RedisCacheService with mocked Redis."""

    def _make_service(self, redis_mock: MagicMock) -> RedisCacheService:
        settings = RedisSettings(
            enabled=True,
            ttl_embedding=3600,
            ttl_retrieval=600,
        )
        client = MagicMock()
        client.client = redis_mock
        return RedisCacheService(client, settings)

    def test_get_embedding_cache_hit(self):
        redis_mock = MagicMock()
        vector = [0.1, 0.2, 0.3]
        redis_mock.get.return_value = json.dumps({"vector": vector, "model": "test"}).encode()
        svc = self._make_service(redis_mock)

        result = svc.get_embedding("some text")
        assert result == vector

    def test_get_embedding_cache_miss(self):
        redis_mock = MagicMock()
        redis_mock.get.return_value = None
        svc = self._make_service(redis_mock)

        assert svc.get_embedding("miss") is None

    def test_get_embedding_handles_redis_error(self):
        redis_mock = MagicMock()
        redis_mock.get.side_effect = Exception("connection error")
        svc = self._make_service(redis_mock)

        assert svc.get_embedding("error") is None

    def test_set_embedding_writes_to_redis(self):
        redis_mock = MagicMock()
        svc = self._make_service(redis_mock)

        svc.set_embedding("text", [1.0, 2.0], model="hash")
        redis_mock.setex.assert_called_once()
        args = redis_mock.setex.call_args[0]
        assert args[0].startswith("rag:emb:")
        assert args[1] == 3600  # ttl

    def test_set_embedding_handles_redis_error(self):
        redis_mock = MagicMock()
        redis_mock.setex.side_effect = Exception("write error")
        svc = self._make_service(redis_mock)
        # Should not raise
        svc.set_embedding("text", [1.0])

    def test_get_embeddings_batch_hit(self):
        redis_mock = MagicMock()
        pipe_mock = MagicMock()
        pipe_mock.execute.return_value = [
            json.dumps({"vector": [0.1]}),
            json.dumps({"vector": [0.2]}),
        ]
        redis_mock.pipeline.return_value = pipe_mock
        svc = self._make_service(redis_mock)

        results = svc.get_embeddings(["a", "b"])
        assert results == [[0.1], [0.2]]

    def test_get_embeddings_batch_partial_miss(self):
        redis_mock = MagicMock()
        pipe_mock = MagicMock()
        pipe_mock.execute.return_value = [
            json.dumps({"vector": [0.1]}),
            None,
        ]
        redis_mock.pipeline.return_value = pipe_mock
        svc = self._make_service(redis_mock)

        results = svc.get_embeddings(["a", "b"])
        assert results == [[0.1], None]

    def test_get_embeddings_batch_redis_error_returns_nones(self):
        redis_mock = MagicMock()
        pipe_mock = MagicMock()
        pipe_mock.execute.side_effect = Exception("pipe error")
        redis_mock.pipeline.return_value = pipe_mock
        svc = self._make_service(redis_mock)

        results = svc.get_embeddings(["a", "b"])
        assert results == [None, None]

    def test_get_embeddings_batch_empty(self):
        redis_mock = MagicMock()
        svc = self._make_service(redis_mock)
        assert svc.get_embeddings([]) == []

    def test_set_embeddings_batch_writes(self):
        redis_mock = MagicMock()
        pipe_mock = MagicMock()
        redis_mock.pipeline.return_value = pipe_mock
        svc = self._make_service(redis_mock)

        svc.set_embeddings(["a", "b"], [[0.1], [0.2]])
        pipe_mock.setex.assert_called()
        pipe_mock.execute.assert_called_once()

    def test_set_embeddings_batch_handles_error(self):
        redis_mock = MagicMock()
        pipe_mock = MagicMock()
        pipe_mock.execute.side_effect = Exception("write error")
        redis_mock.pipeline.return_value = pipe_mock
        svc = self._make_service(redis_mock)
        # Should not raise
        svc.set_embeddings(["a"], [[0.1]])

    def test_set_embeddings_batch_empty(self):
        redis_mock = MagicMock()
        svc = self._make_service(redis_mock)
        svc.set_embeddings([], [])
        redis_mock.pipeline.assert_not_called()

    def test_get_retrieval_cache_hit(self):
        redis_mock = MagicMock()
        results = [{"chunk_id": "c1", "score": 0.9, "text": "hello"}]
        redis_mock.get.return_value = json.dumps({"results": results}).encode()
        svc = self._make_service(redis_mock)

        assert svc.get_retrieval("query", "col") == results

    def test_get_retrieval_cache_miss(self):
        redis_mock = MagicMock()
        redis_mock.get.return_value = None
        svc = self._make_service(redis_mock)

        assert svc.get_retrieval("query", "col") is None

    def test_set_retrieval_writes_to_redis(self):
        redis_mock = MagicMock()
        svc = self._make_service(redis_mock)

        svc.set_retrieval("query", "col", [{"chunk_id": "c1"}])
        redis_mock.setex.assert_called_once()
        args = redis_mock.setex.call_args[0]
        assert args[0].startswith("rag:ret:")
        assert args[1] == 600  # ttl


class TestCachingEmbeddingProvider:
    """Verify the caching wrapper delegates correctly."""

    def test_all_cached(self):
        from rag_mcp.infrastructure.embedding.caching_embedding import (
            CachingEmbeddingProvider,
        )

        delegate = MagicMock()
        delegate.embed_texts.return_value = [[0.1], [0.2]]
        cache = MagicMock()
        cache.get_embeddings.return_value = [[0.1], [0.2]]

        provider = CachingEmbeddingProvider(delegate, cache)
        result = provider.embed_texts(["a", "b"])

        assert result == [[0.1], [0.2]]
        delegate.embed_texts.assert_not_called()

    def test_partial_miss_calls_delegate(self):
        from rag_mcp.infrastructure.embedding.caching_embedding import (
            CachingEmbeddingProvider,
        )

        delegate = MagicMock()
        delegate.embed_texts.return_value = [[0.3]]
        cache = MagicMock()
        cache.get_embeddings.return_value = [[0.1], None]

        provider = CachingEmbeddingProvider(delegate, cache)
        result = provider.embed_texts(["a", "b"])

        assert result == [[0.1], [0.3]]
        delegate.embed_texts.assert_called_once_with(["b"])

    def test_all_miss_calls_delegate(self):
        from rag_mcp.infrastructure.embedding.caching_embedding import (
            CachingEmbeddingProvider,
        )

        delegate = MagicMock()
        delegate.embed_texts.return_value = [[0.1], [0.2]]
        cache = MagicMock()
        cache.get_embeddings.return_value = [None, None]

        provider = CachingEmbeddingProvider(delegate, cache)
        result = provider.embed_texts(["a", "b"])

        assert result == [[0.1], [0.2]]
        delegate.embed_texts.assert_called_once_with(["a", "b"])

    def test_empty_input(self):
        from rag_mcp.infrastructure.embedding.caching_embedding import (
            CachingEmbeddingProvider,
        )

        delegate = MagicMock()
        cache = MagicMock()
        cache.get_embeddings.return_value = []

        provider = CachingEmbeddingProvider(delegate, cache)
        result = provider.embed_texts([])

        assert result == []
        delegate.embed_texts.assert_not_called()


class TestContainerRedisIntegration:
    """Verify container wiring handles Redis gracefully."""

    def test_redis_disabled_no_cache(self):
        """When redis.enabled=false, container creates without cache."""
        from rag_mcp.core.container import ApplicationContainer

        settings = Settings.model_validate({"redis": {"enabled": False}})
        container = ApplicationContainer(settings)
        # embedding_provider should be the raw provider, not wrapped
        from rag_mcp.infrastructure.embedding.caching_embedding import (
            CachingEmbeddingProvider,
        )
        assert not isinstance(container.embedding_provider, CachingEmbeddingProvider)
        container.close()

    def test_redis_enabled_but_unreachable_falls_back(self):
        """When redis.enabled=true but Redis is not running, container still starts."""
        from rag_mcp.core.container import ApplicationContainer

        settings = Settings.model_validate({
            "redis": {
                "enabled": True,
                "host": "192.0.2.1",  # unreachable IP (RFC 5737 test range)
                "socket_timeout": 0.5,
                "cache": {"embedding_enabled": True},
            }
        })
        container = ApplicationContainer(settings)
        # Should still work, just without caching
        from rag_mcp.infrastructure.embedding.caching_embedding import (
            CachingEmbeddingProvider,
        )
        assert not isinstance(container.embedding_provider, CachingEmbeddingProvider)
        container.close()
