"""Document summary use case."""

from __future__ import annotations

from rag_mcp.application.dto.models import DocumentSummaryResponse
from rag_mcp.core.exceptions import NotFoundError


class GetDocumentSummaryUseCase:
    """Return a summary view of a document and its chunks."""

    def __init__(self, collection_manager) -> None:
        self.collection_manager = collection_manager

    def execute(self, document_id: str, collection_name: str | None = None) -> DocumentSummaryResponse:
        """Build a summary response for the requested document."""
        scope = self.collection_manager.get_scope(collection_name)
        document = scope.document_repository.get(document_id)
        if document is None:
            raise NotFoundError(f"Document not found: {document_id}")

        chunks = scope.chunk_repository.list_by_document(document_id)
        summary = self._build_summary(document.content)
        return DocumentSummaryResponse(
            document_id=document.id,
            filename=document.filename,
            source_path=document.source_path,
            doc_type=document.doc_type,
            chunk_count=len(chunks),
            summary=summary,
            trace_id=None,
        )

    def _build_summary(self, content: str, max_length: int = 240) -> str:
        normalized = " ".join(content.split())
        if len(normalized) <= max_length:
            return normalized
        return normalized[: max_length - 3].rstrip() + "..."
