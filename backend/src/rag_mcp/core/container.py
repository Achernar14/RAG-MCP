"""Dependency wiring for the MVP."""

from __future__ import annotations

import logging
from functools import lru_cache

from chromadb.api import shared_system_client

from rag_mcp.application.use_cases.ingest_document import IngestDocumentUseCase
from rag_mcp.application.use_cases.delete_document import DeleteDocumentUseCase
from rag_mcp.application.use_cases.generate_answer import GenerateAnswerUseCase
from rag_mcp.application.use_cases.get_document_detail import GetDocumentDetailUseCase
from rag_mcp.application.use_cases.get_document_summary import GetDocumentSummaryUseCase
from rag_mcp.application.use_cases.get_evaluation_report_detail import GetEvaluationReportDetailUseCase
from rag_mcp.application.use_cases.get_knowledge_status import GetKnowledgeStatusUseCase
from rag_mcp.application.use_cases.get_trace_detail import GetTraceDetailUseCase
from rag_mcp.application.use_cases.rebuild_collection import RebuildCollectionUseCase
from rag_mcp.application.use_cases.list_collections import ListCollectionsUseCase
from rag_mcp.application.use_cases.list_documents import ListDocumentsUseCase
from rag_mcp.application.use_cases.list_evaluation_reports import ListEvaluationReportsUseCase
from rag_mcp.application.use_cases.list_traces import ListTracesUseCase
from rag_mcp.application.use_cases.query_knowledge import QueryKnowledgeUseCase
from rag_mcp.application.use_cases.run_evaluation import RunEvaluationUseCase
from rag_mcp.core.settings import Settings, load_settings, resolve_project_path
from rag_mcp.core.tracing import JsonlTraceCollector
from rag_mcp.infrastructure.repositories.json_evaluation_repository import JsonlEvaluationReportRepository
from rag_mcp.domain.services.hybrid_retrieval import HybridRetrievalService
from rag_mcp.domain.services.retrieval import RetrievalService
from rag_mcp.infrastructure.loaders.compound_loader import CompoundDocumentLoader
from rag_mcp.infrastructure.loaders.pdf_loader import PdfDocumentLoader
from rag_mcp.infrastructure.loaders.text_loader import TextDocumentLoader
from rag_mcp.infrastructure.ingestion.source_inspector import LocalSourceInspector
from rag_mcp.infrastructure.ingestion.source_validator import LocalSourceValidator
from rag_mcp.infrastructure.pipeline import IngestionPipeline
from rag_mcp.infrastructure.prompts.answer_prompt_builder import AnswerPromptBuilder
from rag_mcp.infrastructure.prompts.template_loader import FilePromptTemplateLoader
from rag_mcp.infrastructure.providers.factories import (
    create_embedding_provider,
    create_llm_provider,
    create_reranker,
    create_vision_llm_provider,
)
from rag_mcp.infrastructure.repositories.json_repositories import (
    JsonChunkRepository,
    JsonDocumentRepository,
)
from rag_mcp.infrastructure.repositories.jsonl_trace_repository import JsonlTraceRepository
from rag_mcp.infrastructure.sparse.bm25_store import JsonBm25Store
from rag_mcp.infrastructure.splitters.simple_splitter import SimpleTextSplitter
from rag_mcp.infrastructure.vector_store.chroma_store import ChromaVectorStore
from rag_mcp.infrastructure.vector_store.memory_store import InMemoryVectorStore

logger = logging.getLogger(__name__)


class ApplicationContainer:
    """Owns singleton components used by the MVP."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        vector_store_dir = resolve_project_path(
            self.settings.vector_store.persist_path
        ).parent
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

        self.prompt_template_loader = FilePromptTemplateLoader()
        self.answer_prompt_builder = AnswerPromptBuilder(
            template_loader=self.prompt_template_loader,
            system_prompt_path=self.settings.prompts.answer_system_prompt_path,
            user_prompt_path=self.settings.prompts.answer_user_prompt_path,
        )
        self.loader = CompoundDocumentLoader(
            text_loader=TextDocumentLoader(),
            pdf_loader=PdfDocumentLoader(),
        )
        self.source_inspector = LocalSourceInspector()
        self.source_validator = LocalSourceValidator(
            supported_extensions=settings.ingestion.supported_extensions,
            max_file_size_bytes=settings.ingestion.max_file_size_bytes,
            allow_hidden_files=settings.ingestion.allow_hidden_files,
        )
        self.splitter = SimpleTextSplitter(
            chunk_size=settings.ingestion.chunk_size,
            chunk_overlap=settings.ingestion.chunk_overlap,
            normalize_whitespace=settings.ingestion.normalize_whitespace,
            preserve_paragraph_breaks=settings.ingestion.preserve_paragraph_breaks,
            boundary_scan_chars=settings.ingestion.boundary_scan_chars,
            min_chunk_length=settings.ingestion.min_chunk_length,
        )
        self.pipeline = IngestionPipeline(
            loader=self.loader,
            splitter=self.splitter,
            embedding_provider=self.embedding_provider,
            document_repository=self.document_repository,
            chunk_repository=self.chunk_repository,
            vector_store=self.vector_store,
            sparse_index=self.sparse_index,
            trace_collector=self.trace_collector,
            source_inspector=self.source_inspector,
            source_validator=self.source_validator,
        )
        self.retrieval_service = HybridRetrievalService(
            embedding_provider=self.embedding_provider,
            vector_store=self.vector_store,
            sparse_index=self.sparse_index,
            settings=settings.retrieval,
            reranker=self.reranker,
            redis_cache=self._redis_cache if self.settings.redis.cache.retrieval_enabled else None,
        )
        self.dense_retrieval_service = RetrievalService(
            embedding_provider=self.embedding_provider,
            vector_store=self.vector_store,
        )
        self.ingest_use_case = IngestDocumentUseCase(self.pipeline)
        self.query_use_case = QueryKnowledgeUseCase(
            retrieval_service=self.retrieval_service,
            trace_collector=self.trace_collector,
        )
        self.generate_answer_use_case = GenerateAnswerUseCase(
            query_use_case=self.query_use_case,
            llm_provider=self.llm_provider,
            trace_collector=self.trace_collector,
            answer_prompt_builder=self.answer_prompt_builder,
        )
        self.get_document_summary_use_case = GetDocumentSummaryUseCase(
            document_repository=self.document_repository,
            chunk_repository=self.chunk_repository,
        )
        self.get_document_detail_use_case = GetDocumentDetailUseCase(
            document_repository=self.document_repository,
            chunk_repository=self.chunk_repository,
        )
        self.list_traces_use_case = ListTracesUseCase(
            trace_repository=self.trace_repository,
        )
        self.get_trace_detail_use_case = GetTraceDetailUseCase(
            trace_repository=self.trace_repository,
        )
        self.list_documents_use_case = ListDocumentsUseCase(
            document_repository=self.document_repository,
            chunk_repository=self.chunk_repository,
        )
        self.delete_document_use_case = DeleteDocumentUseCase(
            document_repository=self.document_repository,
            chunk_repository=self.chunk_repository,
            vector_store=self.vector_store,
            sparse_index=self.sparse_index,
        )
        self.knowledge_status_use_case = GetKnowledgeStatusUseCase(
            settings=self.settings,
            document_repository=self.document_repository,
            chunk_repository=self.chunk_repository,
            sparse_index=self.sparse_index,
        )
        self.rebuild_collection_use_case = RebuildCollectionUseCase(
            settings=self.settings,
            document_repository=self.document_repository,
            pipeline=self.pipeline,
            trace_collector=self.trace_collector,
        )
        self.list_collections_use_case = ListCollectionsUseCase(
            settings=self.settings,
            document_repository=self.document_repository,
            chunk_repository=self.chunk_repository,
            sparse_index=self.sparse_index,
        )
        self.run_evaluation_use_case = RunEvaluationUseCase(
            settings=self.settings,
            query_use_case=self.query_use_case,
            evaluation_report_repository=self.evaluation_report_repository,
            trace_collector=self.trace_collector,
        )
        self.list_evaluation_reports_use_case = ListEvaluationReportsUseCase(
            evaluation_report_repository=self.evaluation_report_repository,
        )
        self.get_evaluation_report_detail_use_case = GetEvaluationReportDetailUseCase(
            evaluation_report_repository=self.evaluation_report_repository,
        )

    def close(self) -> None:
        """Release resources held by the container."""
        close_method = getattr(self.vector_store, "close", None)
        if callable(close_method):
            close_method()
        if self._redis_client is not None:
            self._redis_client.close()
        clear_cache = getattr(shared_system_client.SharedSystemClient, "clear_system_cache", None)
        if callable(clear_cache):
            clear_cache()

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
