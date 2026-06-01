"""Dependency wiring -- shared infrastructure + skill-based assembly."""

from __future__ import annotations

import logging
from functools import lru_cache

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
from rag_mcp.infrastructure.repositories.json_repositories import (
    JsonChunkRepository,
    JsonDocumentRepository,
)
from rag_mcp.infrastructure.repositories.jsonl_trace_repository import (
    JsonlTraceRepository,
)
from rag_mcp.infrastructure.sparse.bm25_store import JsonBm25Store
from rag_mcp.infrastructure.vector_store.chroma_store import ChromaVectorStore
from rag_mcp.infrastructure.vector_store.memory_store import InMemoryVectorStore

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
        vs = self.settings.vector_store
        if vs.provider.lower() == "weaviate":
            vector_store_dir = resolve_project_path(vs.weaviate_persistence_data_path).parent
        else:
            vector_store_dir = resolve_project_path(vs.persist_path).parent

        self.trace_collector = JsonlTraceCollector(
            resolve_project_path(settings.observability.trace_path)
        )
        self.trace_repository = JsonlTraceRepository(
            resolve_project_path(settings.observability.trace_path)
        )
        self.evaluation_report_repository = JsonlEvaluationReportRepository(
            resolve_project_path(settings.evaluation.report_path)
        )
        self.document_repository = JsonDocumentRepository(
            vector_store_dir / "documents.json"
        )
        self.chunk_repository = JsonChunkRepository(
            vector_store_dir / "chunks.json"
        )
        self.vector_store = self._create_vector_store()
        self.sparse_index = JsonBm25Store(vector_store_dir / "bm25_index.json")
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
        close_method = getattr(self.vector_store, "close", None)
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

    def _create_vector_store(self):
        provider = self.settings.vector_store.provider.lower()
        if provider == "memory":
            return InMemoryVectorStore()
        if provider == "chroma":
            return ChromaVectorStore(
                persist_path=str(
                    resolve_project_path(self.settings.vector_store.persist_path)
                ),
                collection_name=self.settings.vector_store.collection_name,
            )
        if provider == "weaviate":
            from rag_mcp.infrastructure.vector_store.weaviate_store import WeaviateVectorStore
            return WeaviateVectorStore(
                persistence_data_path=str(
                    resolve_project_path(
                        self.settings.vector_store.weaviate_persistence_data_path
                    )
                ),
                version=self.settings.vector_store.weaviate_version,
                hostname=self.settings.vector_store.weaviate_hostname,
                port=self.settings.vector_store.weaviate_port,
                collection_name=self.settings.vector_store.collection_name,
            )
        raise ValueError(f"Unsupported vector store provider: {provider}")


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
