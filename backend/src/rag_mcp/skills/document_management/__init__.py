"""Document management skill: listing, detail, summary, deletion."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rag_mcp.application.dto.models import (
    DeleteDocumentResponse,
    DocumentDetailResponse,
    DocumentListItemResponse,
    DocumentSummaryResponse,
)
from rag_mcp.core.skill_registry import SkillDescriptor, ToolDescriptor

if TYPE_CHECKING:
    from rag_mcp.core.container import ApplicationContainer
    from rag_mcp.core.settings import Settings


class DocumentManagementSkill:
    """Handles document CRUD operations."""

    @classmethod
    def descriptor(cls) -> SkillDescriptor:
        return SkillDescriptor(
            name="document_management",
            version="1.0.0",
            description="Document listing, detail views, and deletion",
            enabled_by_default=True,
            dependencies=[],
        )

    @classmethod
    def register_tools(cls, container: ApplicationContainer) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name="list_documents",
                description="List documents that are currently ingested.",
                handler=cls._list_documents(container),
                return_type=list[DocumentListItemResponse],
            ),
            ToolDescriptor(
                name="get_document_detail",
                description="Get a detailed document view including chunk breakdown.",
                handler=cls._get_document_detail(container),
                return_type=DocumentDetailResponse,
            ),
            ToolDescriptor(
                name="get_document_summary",
                description="Get a summary view for a document.",
                handler=cls._get_document_summary(container),
                return_type=DocumentSummaryResponse,
            ),
            ToolDescriptor(
                name="delete_document",
                description="Delete a document and remove its vector and sparse index entries.",
                handler=cls._delete_document(container),
                return_type=DeleteDocumentResponse,
            ),
        ]

    @classmethod
    def wire_container(cls, container: ApplicationContainer, settings: Settings) -> None:
        from rag_mcp.application.use_cases.list_documents import ListDocumentsUseCase
        from rag_mcp.application.use_cases.get_document_detail import GetDocumentDetailUseCase
        from rag_mcp.application.use_cases.get_document_summary import GetDocumentSummaryUseCase
        from rag_mcp.application.use_cases.delete_document import DeleteDocumentUseCase

        container.list_documents_use_case = ListDocumentsUseCase(
            collection_manager=container.collection_manager,
        )
        container.get_document_detail_use_case = GetDocumentDetailUseCase(
            collection_manager=container.collection_manager,
        )
        container.get_document_summary_use_case = GetDocumentSummaryUseCase(
            collection_manager=container.collection_manager,
        )
        container.delete_document_use_case = DeleteDocumentUseCase(
            collection_manager=container.collection_manager,
        )

    @staticmethod
    def _list_documents(container: ApplicationContainer):
        def list_documents():
            return container.list_documents_use_case.execute()

        return list_documents

    @staticmethod
    def _get_document_detail(container: ApplicationContainer):
        def get_document_detail(document_id: str):
            return container.get_document_detail_use_case.execute(document_id)

        return get_document_detail

    @staticmethod
    def _get_document_summary(container: ApplicationContainer):
        def get_document_summary(document_id: str):
            return container.get_document_summary_use_case.execute(document_id)

        return get_document_summary

    @staticmethod
    def _delete_document(container: ApplicationContainer):
        def delete_document(document_id: str):
            return container.delete_document_use_case.execute(document_id)

        return delete_document
