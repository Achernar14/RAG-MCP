"""Document listing use case."""

from __future__ import annotations

from rag_mcp.application.dto.models import DocumentListItemResponse


class ListDocumentsUseCase:
    """Return document list items with lightweight statistics."""

    def __init__(self, collection_manager) -> None:
        self.collection_manager = collection_manager

    def execute(self, collection_name: str | None = None) -> list[DocumentListItemResponse]:
        """List all ingested documents with per-document chunk counts."""
        scope = self.collection_manager.get_scope(collection_name)
        documents = sorted(
            scope.document_repository.list_all(),
            key=lambda item: item.updated_at,
            reverse=True,
        )
        return [
            DocumentListItemResponse(
                id=document.id,
                filename=document.filename,
                source_path=document.source_path,
                doc_type=document.doc_type,
                chunk_count=len(scope.chunk_repository.list_by_document(document.id)),
                created_at=document.created_at,
                updated_at=document.updated_at,
            )
            for document in documents
        ]
