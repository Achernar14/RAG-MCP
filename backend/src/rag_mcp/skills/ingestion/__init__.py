"""Ingestion skill: document loading, splitting, embedding, indexing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rag_mcp.application.dto.models import (
    CollectionInfoResponse,
    IngestResponse,
    KnowledgeStatusResponse,
    RebuildCollectionResponse,
)
from rag_mcp.core.skill_registry import SkillDescriptor, ToolDescriptor

if TYPE_CHECKING:
    from rag_mcp.core.container import ApplicationContainer
    from rag_mcp.core.settings import Settings


class IngestionSkill:
    """Handles document ingestion, status, collection rebuild, and listing."""

    @classmethod
    def descriptor(cls) -> SkillDescriptor:
        return SkillDescriptor(
            name="ingestion",
            version="1.0.0",
            description="Document loading, validation, splitting, embedding, and indexing",
            enabled_by_default=True,
            dependencies=[],
        )

    @classmethod
    def register_tools(cls, container: ApplicationContainer) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name="knowledge_ingest",
                description="Ingest a local document into the active knowledge base.",
                handler=cls._knowledge_ingest(container),
                return_type=IngestResponse,
            ),
            ToolDescriptor(
                name="knowledge_status",
                description="Return high-level status for the active knowledge base.",
                handler=cls._knowledge_status(container),
                return_type=KnowledgeStatusResponse,
            ),
            ToolDescriptor(
                name="rebuild_collection",
                description="Rebuild indexes for the active collection from persisted source documents.",
                handler=cls._rebuild_collection(container),
                return_type=RebuildCollectionResponse,
            ),
            ToolDescriptor(
                name="list_collections",
                description="List the active logical collections and index statistics.",
                handler=cls._list_collections(container),
                return_type=list[CollectionInfoResponse],
            ),
        ]

    @classmethod
    def wire_container(cls, container: ApplicationContainer, settings: Settings) -> None:
        from rag_mcp.application.use_cases.ingest_document import IngestDocumentUseCase
        from rag_mcp.application.use_cases.get_knowledge_status import GetKnowledgeStatusUseCase
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

        container.loader = CompoundDocumentLoader(
            text_loader=TextDocumentLoader(),
            pdf_loader=PdfDocumentLoader(),
            confluence_loader=ConfluenceDocumentLoader(),
        )
        container.source_inspector = LocalSourceInspector()
        container.source_validator = LocalSourceValidator(
            supported_extensions=settings.ingestion.supported_extensions,
            max_file_size_bytes=settings.ingestion.max_file_size_bytes,
            allow_hidden_files=settings.ingestion.allow_hidden_files,
        )
        container.splitter = SimpleTextSplitter(
            chunk_size=settings.ingestion.chunk_size,
            chunk_overlap=settings.ingestion.chunk_overlap,
            normalize_whitespace=settings.ingestion.normalize_whitespace,
            preserve_paragraph_breaks=settings.ingestion.preserve_paragraph_breaks,
            boundary_scan_chars=settings.ingestion.boundary_scan_chars,
            min_chunk_length=settings.ingestion.min_chunk_length,
        )
        container.pipeline = IngestionPipeline(
            loader=container.loader,
            splitter=container.splitter,
            embedding_provider=container.embedding_provider,
            document_repository=container.document_repository,
            chunk_repository=container.chunk_repository,
            vector_store=container.vector_store,
            sparse_index=container.sparse_index,
            trace_collector=container.trace_collector,
            source_inspector=container.source_inspector,
            source_validator=container.source_validator,
            collection_manager=container.collection_manager,
        )
        container.ingest_use_case = IngestDocumentUseCase(container.pipeline)
        container.knowledge_status_use_case = GetKnowledgeStatusUseCase(
            settings=settings,
            collection_manager=container.collection_manager,
        )
        container.rebuild_collection_use_case = RebuildCollectionUseCase(
            settings=settings,
            collection_manager=container.collection_manager,
            pipeline=container.pipeline,
            trace_collector=container.trace_collector,
        )
        container.list_collections_use_case = ListCollectionsUseCase(
            settings=settings,
            collection_manager=container.collection_manager,
        )

    # -- Tool handlers --

    @staticmethod
    def _knowledge_ingest(container: ApplicationContainer):
        from rag_mcp.application.dto.models import IngestRequest

        def knowledge_ingest(path: str, force_rebuild: bool = False):
            return container.ingest_use_case.execute(
                IngestRequest(path=path, force_rebuild=force_rebuild)
            )

        return knowledge_ingest

    @staticmethod
    def _knowledge_status(container: ApplicationContainer):
        def knowledge_status():
            return container.knowledge_status_use_case.execute()

        return knowledge_status

    @staticmethod
    def _rebuild_collection(container: ApplicationContainer):
        def rebuild_collection(collection_name: str | None = None):
            return container.rebuild_collection_use_case.execute(collection_name)

        return rebuild_collection

    @staticmethod
    def _list_collections(container: ApplicationContainer):
        def list_collections():
            return container.list_collections_use_case.execute()

        return list_collections
