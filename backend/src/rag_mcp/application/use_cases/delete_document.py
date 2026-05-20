"""Delete document use case."""

from __future__ import annotations

from rag_mcp.application.dto.models import DeleteDocumentResponse
from rag_mcp.core.exceptions import NotFoundError


class DeleteDocumentUseCase:
    """Delete a document and all associated index entries."""

    def __init__(self, document_repository, chunk_repository, vector_store, sparse_index) -> None:
        self.document_repository = document_repository
        self.chunk_repository = chunk_repository
        self.vector_store = vector_store
        self.sparse_index = sparse_index

    def execute(self, document_id: str) -> DeleteDocumentResponse:
        """Delete the document from metadata, dense store, and sparse index."""
        document = self.document_repository.get(document_id)
        if document is None:
            raise NotFoundError(f"Document not found: {document_id}")

        deleted_chunk_count = self.chunk_repository.delete_by_document(document_id)
        self.vector_store.delete_by_document(document_id)
        self.sparse_index.delete_by_document(document_id)
        self.document_repository.delete(document_id)

        return DeleteDocumentResponse(
            document_id=document_id,
            deleted_chunk_count=deleted_chunk_count,
            trace_id=None,
        )
