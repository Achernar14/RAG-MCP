"""In-memory repositories for MVP development."""

from __future__ import annotations

from rag_mcp.domain.entities.models import Chunk, Document


class InMemoryDocumentRepository:
    """In-memory document persistence."""

    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}

    def save(self, document: Document) -> None:
        self.documents[document.id] = document

    def list_all(self) -> list[Document]:
        return list(self.documents.values())

    def get(self, document_id: str) -> Document | None:
        return self.documents.get(document_id)

    def get_by_source_path(self, source_path: str) -> Document | None:
        for document in self.documents.values():
            if document.source_path == source_path:
                return document
        return None

    def delete(self, document_id: str) -> bool:
        if document_id not in self.documents:
            return False
        del self.documents[document_id]
        return True


class InMemoryChunkRepository:
    """In-memory chunk persistence."""

    def __init__(self) -> None:
        self.chunks_by_document: dict[str, list[Chunk]] = {}

    def save_many(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        self.chunks_by_document[chunks[0].document_id] = list(chunks)

    def list_by_document(self, document_id: str) -> list[Chunk]:
        return list(self.chunks_by_document.get(document_id, []))

    def delete_by_document(self, document_id: str) -> int:
        chunks = self.chunks_by_document.pop(document_id, [])
        return len(chunks)
