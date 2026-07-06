"""Collection summary use case."""

from __future__ import annotations

from rag_mcp.application.dto.models import CollectionInfoResponse


class ListCollectionsUseCase:
    """Return information about available collections."""

    def __init__(self, settings, collection_manager) -> None:
        self.settings = settings
        self.collection_manager = collection_manager

    def execute(self) -> list[CollectionInfoResponse]:
        """List all collections with local statistics."""
        result: list[CollectionInfoResponse] = []
        for name in self.collection_manager.list_collections():
            scope = self.collection_manager.get_scope(name)
            documents = scope.document_repository.list_all()
            chunk_count = sum(
                len(scope.chunk_repository.list_by_document(doc.id))
                for doc in documents
            )
            result.append(
                CollectionInfoResponse(
                    name=name,
                    document_count=len(documents),
                    chunk_count=chunk_count,
                    vector_store_provider=self.settings.vector_store.provider,
                    sparse_index_present=scope.sparse_index.exists(),
                )
            )
        return result
