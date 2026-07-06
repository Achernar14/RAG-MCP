"""Dependency wiring -- shared infrastructure + skill-based assembly."""

from __future__ import annotations

import logging
from functools import lru_cache

from rag_mcp.core.collection_manager import CollectionManager
from rag_mcp.core.settings import Settings, load_settings, resolve_project_path
from rag_mcp.core.skill_registry import SkillRegistry
from rag_mcp.core.tracing import JsonlTraceCollector
from rag_mcp.infrastructure.providers.factories import (
    create_embedding_provider,
    create_llm_provider,
    create_reranker,
    create_vision_llm_provider,
)
from rag_mcp.infrastructure.repositories.json_evaluation_repository import (
    JsonlEvaluationReportRepository,
)
from rag_mcp.infrastructure.repositories.jsonl_trace_repository import (
    JsonlTraceRepository,
)

logger = logging.getLogger(__name__)


def _create_skill_registry() -> SkillRegistry:
    """Create and populate the skill registry with all built-in skills."""
    registry = SkillRegistry()

    from rag_mcp.skills.ingestion import IngestionSkill
    from rag_mcp.skills.retrieval import RetrievalSkill
    from rag_mcp.skills.generation import GenerationSkill
    from rag_mcp.skills.document_management import DocumentManagementSkill
    from rag_mcp.skills.evaluation import EvaluationSkill
    from rag_mcp.skills.observability import ObservabilitySkill

    registry.register(IngestionSkill)
    registry.register(RetrievalSkill)
    registry.register(GenerationSkill)
    registry.register(DocumentManagementSkill)
    registry.register(EvaluationSkill)
    registry.register(ObservabilitySkill)

    return registry


class ApplicationContainer:
    """Owns singleton components -- shared infrastructure + per-skill use cases."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        # --- Phase A: Shared infrastructure (always wired) ---
        self.trace_collector = JsonlTraceCollector(
            resolve_project_path(settings.observability.trace_path)
        )
        self.trace_repository = JsonlTraceRepository(
            resolve_project_path(settings.observability.trace_path)
        )
        self.evaluation_report_repository = JsonlEvaluationReportRepository(
            resolve_project_path(settings.evaluation.report_path)
        )

        # Collection manager — supports multi-collection data isolation
        self.collection_manager = CollectionManager(settings)

        # Default scope convenience (used by most single-collection operations)
        self._default_scope = self.collection_manager.default_scope

        self.reranker = create_reranker(self.settings)
        self.vision_llm_provider = create_vision_llm_provider(self.settings)
        self.llm_provider = create_llm_provider(self.settings)

        # Redis cache (optional)
        self._redis_client = None
        self._redis_cache = self._create_redis_cache()
        self.embedding_provider = self._create_embedding_with_cache()

        # --- Phase B: Per-skill wiring (conditional) ---
        self._skill_registry = _create_skill_registry()
        self._enable_skills_from_settings()
        self._skill_registry.wire_all(self, settings)

    # -- Backward-compatible repository / store properties (default collection) --

    @property
    def vector_store(self):
        """Vector store for the default collection."""
        return self._default_scope.vector_store

    @property
    def document_repository(self):
        """Document repository for the default collection."""
        return self._default_scope.document_repository

    @property
    def chunk_repository(self):
        """Chunk repository for the default collection."""
        return self._default_scope.chunk_repository

    @property
    def sparse_index(self):
        """BM25 sparse index for the default collection."""
        return self._default_scope.sparse_index

    # -- Collection-aware helpers --

    def get_scope(self, collection_name: str | None = None):
        """Return the :class:`CollectionScope` for *collection_name*."""
        return self.collection_manager.get_scope(collection_name)

    def switch_default_collection(self, collection_name: str) -> None:
        """Update the default collection scope (used by multi-collection flows)."""
        self._default_scope = self.collection_manager.get_scope(collection_name)

    # -- Skill management --

    @property
    def skill_registry(self) -> SkillRegistry:
        return self._skill_registry

    def _enable_skills_from_settings(self) -> None:
        flags = self.settings.skills
        mapping = {
            "ingestion": flags.ingestion,
            "retrieval": flags.retrieval,
            "generation": flags.generation,
            "document_management": flags.document_management,
            "evaluation": flags.evaluation,
            "observability": flags.observability,
        }
        for name, enabled in mapping.items():
            if enabled:
                self._skill_registry.enable(name)

    # -- Resource management --

    def close(self) -> None:
        """Release resources held by the container."""
        for scope in self.collection_manager._scopes.values():
            close_method = getattr(scope.vector_store, "close", None)
            if callable(close_method):
                close_method()
        if self._redis_client is not None:
            self._redis_client.close()

    # -- Shared infrastructure factories --

    def _create_redis_cache(self):
        """Create a RedisCacheService if Redis is enabled and reachable."""
        if not self.settings.redis.enabled:
            return None
        try:
            from rag_mcp.infrastructure.redis.cache import RedisCacheService
            from rag_mcp.infrastructure.redis.client import RedisClient

            client = RedisClient(self.settings.redis)
            if not client.ping():
                logger.warning("Redis ping failed, caching disabled")
                client.close()
                return None
            self._redis_client = client
            return RedisCacheService(client, self.settings.redis)
        except ImportError:
            logger.info("redis package not installed, caching disabled")
            return None
        except Exception:
            logger.warning("Redis initialization failed, caching disabled", exc_info=True)
            return None

    def _create_embedding_with_cache(self):
        """Create embedding provider, optionally wrapped with caching."""
        provider = create_embedding_provider(self.settings)
        if (
            self._redis_cache is not None
            and self.settings.redis.cache.embedding_enabled
        ):
            from rag_mcp.infrastructure.embedding.caching_embedding import (
                CachingEmbeddingProvider,
            )
            return CachingEmbeddingProvider(provider, self._redis_cache)
        return provider

    # _create_vector_store is now provided by CollectionManager._build_vector_store


@lru_cache(maxsize=1)
def get_container() -> ApplicationContainer:
    """Return a singleton application container."""
    return ApplicationContainer(load_settings())


def reset_container() -> None:
    """Clear the singleton container and close underlying resources."""
    if get_container.cache_info().currsize:
        container = get_container()
        container.close()
    get_container.cache_clear()
    try:
        from rag_mcp.mcp.sdk_server import reset_fastmcp_server
    except Exception:
        return
    reset_fastmcp_server()
