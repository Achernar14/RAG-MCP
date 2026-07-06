"""Document detail use case."""

from __future__ import annotations

from rag_mcp.application.dto.models import DocumentChunkDetailResponse
from rag_mcp.application.dto.models import DocumentDetailResponse
from rag_mcp.application.dto.models import DocumentAssetDetailResponse
from rag_mcp.core.exceptions import NotFoundError


class GetDocumentDetailUseCase:
    """Return a detailed view of a document and its chunks."""

    def __init__(self, collection_manager) -> None:
        self.collection_manager = collection_manager

    def execute(self, document_id: str, collection_name: str | None = None) -> DocumentDetailResponse:
        """Build a detailed response for the requested document."""
        scope = self.collection_manager.get_scope(collection_name)
        document = scope.document_repository.get(document_id)
        if document is None:
            raise NotFoundError(f"Document not found: {document_id}")

        chunks = sorted(
            scope.chunk_repository.list_by_document(document_id),
            key=lambda item: item.chunk_index,
        )
        assets = document.metadata.get("assets", [])
        return DocumentDetailResponse(
            document_id=document.id,
            filename=document.filename,
            source_path=document.source_path,
            doc_type=document.doc_type,
            content_length=len(document.content),
            chunk_count=len(chunks),
            created_at=document.created_at,
            updated_at=document.updated_at,
            metadata=document.metadata,
            chunks=[
                DocumentChunkDetailResponse(
                    chunk_id=chunk.id,
                    chunk_index=chunk.chunk_index,
                    start_offset=chunk.start_offset,
                    end_offset=chunk.end_offset,
                    text=chunk.text,
                )
                for chunk in chunks
            ],
            assets=[
                DocumentAssetDetailResponse(
                    asset_id=str(item.get("asset_id")),
                    asset_type=str(item.get("asset_type", "unknown")),
                    page_number=item.get("page_number"),
                    storage_path=item.get("storage_path"),
                    caption=item.get("caption"),
                    status=item.get("status"),
                    metadata=item.get("metadata", {}),
                )
                for item in assets
            ],
            trace_id=None,
        )
