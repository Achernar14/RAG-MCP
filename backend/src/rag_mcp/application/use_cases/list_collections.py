"""Collection summary use case."""

from __future__ import annotations

from rag_mcp.application.dto.models import CollectionInfoResponse


class ListCollectionsUseCase:
    """Return information about available collections."""

    def __init__(self, settings, document_repository, chunk_repository, sparse_index) -> None:
        self.settings = settings
        self.document_repository = document_repository
        self.chunk_repository = chunk_repository
        self.sparse_index = sparse_index

    def execute(self) -> list[CollectionInfoResponse]:
        """List the currently configured collection with local statistics."""
        documents = self.document_repository.list_all()
        chunk_count = sum(len(self.chunk_repository.list_by_document(doc.id)) for doc in documents)
        sparse_index_present = self.sparse_index.exists()
        return [
            CollectionInfoResponse(
                name=self.settings.vector_store.collection_name,
                document_count=len(documents),
                chunk_count=chunk_count,
                vector_store_provider=self.settings.vector_store.provider,
                sparse_index_present=sparse_index_present,
            )
        ]
