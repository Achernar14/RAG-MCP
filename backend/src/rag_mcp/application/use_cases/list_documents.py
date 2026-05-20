"""Document listing use case."""

from __future__ import annotations

from rag_mcp.application.dto.models import DocumentListItemResponse


class ListDocumentsUseCase:
    """Return document list items with lightweight statistics."""

    def __init__(self, document_repository, chunk_repository) -> None:
        self.document_repository = document_repository
        self.chunk_repository = chunk_repository

    def execute(self) -> list[DocumentListItemResponse]:
        """List all ingested documents with per-document chunk counts."""
        documents = sorted(
            self.document_repository.list_all(),
            key=lambda item: item.updated_at,
            reverse=True,
        )
        return [
            DocumentListItemResponse(
                id=document.id,
                filename=document.filename,
                source_path=document.source_path,
                doc_type=document.doc_type,
                chunk_count=len(self.chunk_repository.list_by_document(document.id)),
                created_at=document.created_at,
                updated_at=document.updated_at,
            )
            for document in documents
        ]
