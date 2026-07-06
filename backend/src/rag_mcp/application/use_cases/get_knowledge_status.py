"""Knowledge-base status use case."""

from __future__ import annotations

from rag_mcp.application.dto.models import KnowledgeStatusResponse


class GetKnowledgeStatusUseCase:
    """Return operational statistics for a collection."""

    def __init__(self, settings, collection_manager) -> None:
        self.settings = settings
        self.collection_manager = collection_manager

    def execute(self, collection_name: str | None = None) -> KnowledgeStatusResponse:
        """Build a status summary from the collection's repositories."""
        scope = self.collection_manager.get_scope(collection_name)
        documents = scope.document_repository.list_all()
        chunk_count = sum(
            len(scope.chunk_repository.list_by_document(doc.id)) for doc in documents
        )
        return KnowledgeStatusResponse(
            collection_name=scope.name,
            document_count=len(documents),
            chunk_count=chunk_count,
            vector_store_provider=self.settings.vector_store.provider,
            embedding_provider=self.settings.embedding.provider,
            sparse_index_present=scope.sparse_index.exists(),
        )
