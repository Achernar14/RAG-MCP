"""Delete document use case."""

from __future__ import annotations

from rag_mcp.application.dto.models import DeleteDocumentResponse
from rag_mcp.core.exceptions import NotFoundError


class DeleteDocumentUseCase:
    """Delete a document and all associated index entries."""

    def __init__(self, collection_manager) -> None:
        self.collection_manager = collection_manager

    def execute(self, document_id: str, collection_name: str | None = None) -> DeleteDocumentResponse:
        """Delete the document from metadata, dense store, and sparse index."""
        scope = self.collection_manager.get_scope(collection_name)
        document = scope.document_repository.get(document_id)
        if document is None:
            raise NotFoundError(f"Document not found: {document_id}")

        deleted_chunk_count = scope.chunk_repository.delete_by_document(document_id)
        scope.vector_store.delete_by_document(document_id)
        scope.sparse_index.delete_by_document(document_id)
        scope.document_repository.delete(document_id)

        return DeleteDocumentResponse(
            document_id=document_id,
            deleted_chunk_count=deleted_chunk_count,
            trace_id=None,
        )
