"""Retrieval skill: hybrid dense + sparse retrieval with reranking."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rag_mcp.application.dto.models import QueryResponse
from rag_mcp.core.skill_registry import SkillDescriptor, ToolDescriptor

if TYPE_CHECKING:
    from rag_mcp.core.container import ApplicationContainer
    from rag_mcp.core.settings import Settings


class RetrievalSkill:
    """Handles hybrid retrieval over the knowledge base."""

    @classmethod
    def descriptor(cls) -> SkillDescriptor:
        return SkillDescriptor(
            name="retrieval",
            version="1.0.0",
            description="Hybrid dense + sparse retrieval with reranking",
            enabled_by_default=True,
            dependencies=["ingestion"],
        )

    @classmethod
    def register_tools(cls, container: ApplicationContainer) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name="knowledge_query",
                description="Run hybrid retrieval over the active knowledge base.",
                handler=cls._knowledge_query(container),
                return_type=QueryResponse,
            ),
        ]

    @classmethod
    def wire_container(cls, container: ApplicationContainer, settings: Settings) -> None:
        from rag_mcp.application.use_cases.query_knowledge import QueryKnowledgeUseCase
        from rag_mcp.domain.services.hybrid_retrieval import HybridRetrievalService
        from rag_mcp.domain.services.retrieval import RetrievalService

        container.retrieval_service = HybridRetrievalService(
            embedding_provider=container.embedding_provider,
            vector_store=container.vector_store,
            sparse_index=container.sparse_index,
            settings=settings.retrieval,
            reranker=container.reranker,
            redis_cache=(
                container._redis_cache
                if settings.redis.cache.retrieval_enabled
                else None
            ),
        )
        container.dense_retrieval_service = RetrievalService(
            embedding_provider=container.embedding_provider,
            vector_store=container.vector_store,
        )
        container.query_use_case = QueryKnowledgeUseCase(
            retrieval_service=container.retrieval_service,
            trace_collector=container.trace_collector,
        )

    @staticmethod
    def _knowledge_query(container: ApplicationContainer):
        from rag_mcp.application.dto.models import QueryRequest

        def knowledge_query(query: str, top_k: int = 5):
            return container.query_use_case.execute(QueryRequest(query=query, top_k=top_k))

        return knowledge_query
