"""RAG system assembly — a single factory function that creates and wires
all components in dependency order.

Replaces the old Skill/Container/Registry architecture with a flat,
sequential assembly function.  The resulting :class:`RAGSystem` object
exposes everything the REST and MCP entry points need.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache

from rag_mcp.core.collection_manager import CollectionManager
from rag_mcp.core.settings import Settings, load_settings, resolve_project_path
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


# ═══════════════════════════════════════════════════════════════════════════
# RAGSystem — a flat object that holds all wired components
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class RAGSystem:
    """All components of the RAG system, wired and ready to use."""

    settings: Settings = field(default_factory=lambda: None)  # type: ignore[assignment]

    # -- shared infrastructure --
    trace_collector: object = field(default=None)
    trace_repository: object = field(default=None)
    evaluation_report_repository: object = field(default=None)
    collection_manager: object = field(default=None)
    embedding_provider: object = field(default=None)
    llm_provider: object = field(default=None)
    reranker: object | None = field(default=None)

    # -- ingestion --
    loader: object = field(default=None)
    splitter: object = field(default=None)
    pipeline: object = field(default=None)
    rebuild_collection_use_case: object = field(default=None)
    list_collections_use_case: object = field(default=None)

    # -- retrieval --
    retrieval_service: object = field(default=None)
    query_use_case: object = field(default=None)  # kept for eval compat

    # -- generation --
    answer_prompt_builder: object = field(default=None)

    # -- document management --
    list_documents_use_case: object = field(default=None)
    get_document_detail_use_case: object = field(default=None)
    get_document_summary_use_case: object = field(default=None)
    delete_document_use_case: object = field(default=None)

    # -- evaluation --
    run_evaluation_use_case: object = field(default=None)
    list_evaluation_reports_use_case: object = field(default=None)
    get_evaluation_report_detail_use_case: object = field(default=None)

    # -- observability --
    list_traces_use_case: object = field(default=None)
    get_trace_detail_use_case: object = field(default=None)

    # -- optional --
    _redis_client: object = field(default=None, repr=False)

    # -- default-collection shortcuts --
    @property
    def vector_store(self):
        return self.collection_manager.default_scope.vector_store

    @property
    def document_repository(self):
        return self.collection_manager.default_scope.document_repository

    @property
    def chunk_repository(self):
        return self.collection_manager.default_scope.chunk_repository

    @property
    def sparse_index(self):
        return self.collection_manager.default_scope.sparse_index

    # -- test compatibility (delegate to handlers) --

    @property
    def ingest_use_case(self):
        from rag_mcp.application.handlers import ingest_document as _fn
        class _W:
            def execute(self2, request):
                return _fn(self, request.path, request.force_rebuild,
                           request.collection_name)
        return _W()

    @property
    def generate_answer_use_case(self):
        from rag_mcp.application.handlers import generate_answer as _fn
        from rag_mcp.application.handlers import generate_answer_stream as _sfn
        class _W:
            def execute(self2, request):
                return _fn(self, request.query, request.top_k, request.collection_name)
            def execute_stream(self2, request):
                return _sfn(self, request.query, request.top_k, request.collection_name)
        return _W()

    def close(self) -> None:
        """Release resources held by the system."""
        for scope in self.collection_manager._scopes.values():
            close_method = getattr(scope.vector_store, "close", None)
            if callable(close_method):
                close_method()
        if self._redis_client is not None:
            self._redis_client.close()


# ═══════════════════════════════════════════════════════════════════════════
# Factory function
# ═══════════════════════════════════════════════════════════════════════════


def create_rag_system(settings: Settings | None = None) -> RAGSystem:
    """Create and fully wire a :class:`RAGSystem` from *settings*.

    When *settings* is ``None`` the default configuration is loaded
    (``load_settings()``).  All components — Providers, Services, Use
    Cases, Loaders, Splitters, Pipeline — are created in dependency
    order inside this single function.
    """
    if settings is None:
        settings = load_settings()

    rag = RAGSystem(settings=settings)

    # ── 1. Shared infrastructure ──────────────────────────────────────

    rag.trace_collector = JsonlTraceCollector(
        resolve_project_path(settings.observability.trace_path)
    )
    rag.trace_repository = JsonlTraceRepository(
        resolve_project_path(settings.observability.trace_path)
    )
    rag.evaluation_report_repository = JsonlEvaluationReportRepository(
        resolve_project_path(settings.evaluation.report_path)
    )

    rag.collection_manager = CollectionManager(settings)
    rag.reranker = create_reranker(settings)
    _vision = create_vision_llm_provider(settings)  # currently None
    rag.llm_provider = create_llm_provider(settings)

    _redis_cache, _redis_client = _create_redis_cache(settings)
    rag._redis_client = _redis_client
    rag.embedding_provider = _create_embedding_with_cache(settings, _redis_cache)

    # ── 2. Ingestion ──────────────────────────────────────────────────

    _wire_ingestion(rag, settings)

    # ── 3. Retrieval ──────────────────────────────────────────────────

    _wire_retrieval(rag, settings, _redis_cache)

    # ── 4. Generation ─────────────────────────────────────────────────

    _wire_generation(rag, settings)

    # ── 5. Document management ────────────────────────────────────────

    _wire_document_management(rag, settings)

    # ── 6. Evaluation ─────────────────────────────────────────────────

    _wire_evaluation(rag, settings)

    # ── 7. Observability ──────────────────────────────────────────────

    _wire_observability(rag, settings)

    return rag


# ═══════════════════════════════════════════════════════════════════════════
# Internal wiring helpers (one per subsystem)
# ═══════════════════════════════════════════════════════════════════════════


def _wire_ingestion(rag: RAGSystem, settings: Settings) -> None:
    from rag_mcp.application.use_cases.rebuild_collection import RebuildCollectionUseCase
    from rag_mcp.application.use_cases.list_collections import ListCollectionsUseCase
    from rag_mcp.infrastructure.loaders.compound_loader import CompoundDocumentLoader
    from rag_mcp.infrastructure.loaders.confluence_loader import ConfluenceDocumentLoader
    from rag_mcp.infrastructure.loaders.pdf_loader import PdfDocumentLoader
    from rag_mcp.infrastructure.loaders.text_loader import TextDocumentLoader
    from rag_mcp.infrastructure.ingestion.source_inspector import LocalSourceInspector
    from rag_mcp.infrastructure.ingestion.source_validator import LocalSourceValidator
    from rag_mcp.infrastructure.splitters.simple_splitter import SimpleTextSplitter
    from rag_mcp.infrastructure.pipeline import IngestionPipeline

    rag.loader = CompoundDocumentLoader(
        text_loader=TextDocumentLoader(),
        pdf_loader=PdfDocumentLoader(),
        confluence_loader=ConfluenceDocumentLoader(),
    )
    rag.splitter = SimpleTextSplitter(
        chunk_size=settings.ingestion.chunk_size,
        chunk_overlap=settings.ingestion.chunk_overlap,
        normalize_whitespace=settings.ingestion.normalize_whitespace,
        preserve_paragraph_breaks=settings.ingestion.preserve_paragraph_breaks,
        boundary_scan_chars=settings.ingestion.boundary_scan_chars,
        min_chunk_length=settings.ingestion.min_chunk_length,
    )
    rag.pipeline = IngestionPipeline(
        loader=rag.loader,
        splitter=rag.splitter,
        embedding_provider=rag.embedding_provider,
        document_repository=rag.document_repository,
        chunk_repository=rag.chunk_repository,
        vector_store=rag.vector_store,
        sparse_index=rag.sparse_index,
        trace_collector=rag.trace_collector,
        source_inspector=LocalSourceInspector(),
        source_validator=LocalSourceValidator(
            supported_extensions=settings.ingestion.supported_extensions,
            max_file_size_bytes=settings.ingestion.max_file_size_bytes,
            allow_hidden_files=settings.ingestion.allow_hidden_files,
        ),
        collection_manager=rag.collection_manager,
    )
    rag.rebuild_collection_use_case = RebuildCollectionUseCase(
        settings=settings, collection_manager=rag.collection_manager,
        pipeline=rag.pipeline, trace_collector=rag.trace_collector,
    )
    rag.list_collections_use_case = ListCollectionsUseCase(
        settings=settings, collection_manager=rag.collection_manager,
    )


def _wire_retrieval(rag: RAGSystem, settings: Settings, redis_cache) -> None:
    from rag_mcp.domain.services.hybrid_retrieval import HybridRetrievalService

    rag.retrieval_service = HybridRetrievalService(
        embedding_provider=rag.embedding_provider,
        vector_store=rag.vector_store,
        sparse_index=rag.sparse_index,
        settings=settings.retrieval,
        reranker=rag.reranker,
        redis_cache=redis_cache if settings.redis.cache.retrieval_enabled else None,
    )
    # Thin query wrapper kept for eval compatibility
    from rag_mcp.application.use_cases.query_knowledge import QueryKnowledgeUseCase
    rag.query_use_case = QueryKnowledgeUseCase(
        retrieval_service=rag.retrieval_service,
        trace_collector=rag.trace_collector,
    )


def _wire_generation(rag: RAGSystem, settings: Settings) -> None:
    from rag_mcp.infrastructure.prompts.answer_prompt_builder import AnswerPromptBuilder
    from rag_mcp.infrastructure.prompts.template_loader import FilePromptTemplateLoader

    rag.answer_prompt_builder = AnswerPromptBuilder(
        template_loader=FilePromptTemplateLoader(),
        system_prompt_path=settings.prompts.answer_system_prompt_path,
        user_prompt_path=settings.prompts.answer_user_prompt_path,
    )


def _wire_document_management(rag: RAGSystem, settings: Settings) -> None:
    from rag_mcp.application.use_cases.list_documents import ListDocumentsUseCase
    from rag_mcp.application.use_cases.get_document_detail import GetDocumentDetailUseCase
    from rag_mcp.application.use_cases.get_document_summary import GetDocumentSummaryUseCase
    from rag_mcp.application.use_cases.delete_document import DeleteDocumentUseCase

    rag.list_documents_use_case = ListDocumentsUseCase(
        collection_manager=rag.collection_manager,
    )
    rag.get_document_detail_use_case = GetDocumentDetailUseCase(
        collection_manager=rag.collection_manager,
    )
    rag.get_document_summary_use_case = GetDocumentSummaryUseCase(
        collection_manager=rag.collection_manager,
    )
    rag.delete_document_use_case = DeleteDocumentUseCase(
        collection_manager=rag.collection_manager,
    )


def _wire_evaluation(rag: RAGSystem, settings: Settings) -> None:
    from rag_mcp.application.use_cases.run_evaluation import RunEvaluationUseCase
    from rag_mcp.application.use_cases.list_evaluation_reports import (
        ListEvaluationReportsUseCase,
    )
    from rag_mcp.application.use_cases.get_evaluation_report_detail import (
        GetEvaluationReportDetailUseCase,
    )

    rag.run_evaluation_use_case = RunEvaluationUseCase(
        settings=settings,
        query_use_case=rag.query_use_case,
        evaluation_report_repository=rag.evaluation_report_repository,
        trace_collector=rag.trace_collector,
    )
    rag.list_evaluation_reports_use_case = ListEvaluationReportsUseCase(
        evaluation_report_repository=rag.evaluation_report_repository,
    )
    rag.get_evaluation_report_detail_use_case = GetEvaluationReportDetailUseCase(
        evaluation_report_repository=rag.evaluation_report_repository,
    )


def _wire_observability(rag: RAGSystem, settings: Settings) -> None:
    from rag_mcp.application.use_cases.list_traces import ListTracesUseCase
    from rag_mcp.application.use_cases.get_trace_detail import GetTraceDetailUseCase

    rag.list_traces_use_case = ListTracesUseCase(
        trace_repository=rag.trace_repository,
    )
    rag.get_trace_detail_use_case = GetTraceDetailUseCase(
        trace_repository=rag.trace_repository,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Singleton + helpers
# ═══════════════════════════════════════════════════════════════════════════


@lru_cache(maxsize=1)
def get_rag() -> RAGSystem:
    """Return the singleton :class:`RAGSystem`."""
    return create_rag_system()


def reset_rag() -> None:
    """Clear the singleton and close resources."""
    if get_rag.cache_info().currsize:
        rag = get_rag()
        for scope in rag.collection_manager._scopes.values():
            close_m = getattr(scope.vector_store, "close", None)
            if callable(close_m):
                close_m()
        if rag._redis_client is not None:
            rag._redis_client.close()
    get_rag.cache_clear()
    try:
        from rag_mcp.mcp.sdk_server import reset_fastmcp_server
        reset_fastmcp_server()
    except Exception:
        pass


def _create_redis_cache(settings: Settings):
    """Create a RedisCacheService if Redis is enabled and reachable."""
    if not settings.redis.enabled:
        return None, None
    try:
        from rag_mcp.infrastructure.redis.cache import RedisCacheService
        from rag_mcp.infrastructure.redis.client import RedisClient

        client = RedisClient(settings.redis)
        if not client.ping():
            logger.warning("Redis ping failed, caching disabled")
            client.close()
            return None, None
        return RedisCacheService(client, settings.redis), client
    except ImportError:
        logger.info("redis package not installed, caching disabled")
        return None, None
    except Exception:
        logger.warning("Redis initialization failed, caching disabled", exc_info=True)
        return None, None


def _create_embedding_with_cache(settings: Settings, redis_cache):
    """Create embedding provider, optionally wrapped with caching."""
    provider = create_embedding_provider(settings)
    if redis_cache is not None and settings.redis.cache.embedding_enabled:
        from rag_mcp.infrastructure.embedding.caching_embedding import (
            CachingEmbeddingProvider,
        )
        return CachingEmbeddingProvider(provider, redis_cache)
    return provider
