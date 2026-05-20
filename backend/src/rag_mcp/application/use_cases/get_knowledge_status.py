"""Knowledge-base status use case."""

from __future__ import annotations

from rag_mcp.application.dto.models import KnowledgeStatusResponse


class GetKnowledgeStatusUseCase:
    """Return operational statistics for the active collection."""

    def __init__(self, settings, document_repository, chunk_repository, sparse_index) -> None:
        self.settings = settings
        self.document_repository = document_repository
        self.chunk_repository = chunk_repository
        self.sparse_index = sparse_index

    def execute(self) -> KnowledgeStatusResponse:
        """Build a status summary from the current repositories."""
        documents = self.document_repository.list_all()
        chunk_count = sum(len(self.chunk_repository.list_by_document(doc.id)) for doc in documents)
        return KnowledgeStatusResponse(
            collection_name=self.settings.vector_store.collection_name,
            document_count=len(documents),
            chunk_count=chunk_count,
            vector_store_provider=self.settings.vector_store.provider,
            embedding_provider=self.settings.embedding.provider,
            sparse_index_present=self.sparse_index.exists(),
        )
