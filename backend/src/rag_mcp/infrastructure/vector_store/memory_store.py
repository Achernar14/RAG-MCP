"""In-memory vector store for MVP development."""

from __future__ import annotations

import math

from rag_mcp.domain.entities.models import ChunkRecord, RetrievalResult


class InMemoryVectorStore:
    """A simple in-memory dense vector store."""

    def __init__(self) -> None:
        self.records: dict[str, ChunkRecord] = {}

    def upsert(self, records: list[ChunkRecord]) -> None:
        """Upsert chunk records in memory."""
        for record in records:
            self.records[record.id] = record

    def query(self, query_vector: list[float], top_k: int) -> list[RetrievalResult]:
        """Return top-k results by cosine similarity."""
        scored = [
            (
                self._cosine_similarity(query_vector, record.dense_vector),
                record,
            )
            for record in self.records.values()
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            RetrievalResult(
                chunk_id=record.id,
                score=score,
                text=record.text,
                metadata=record.metadata,
            )
            for score, record in scored[:top_k]
        ]

    def delete_by_document(self, document_id: str) -> int:
        keys = [key for key, record in self.records.items() if record.document_id == document_id]
        for key in keys:
            del self.records[key]
        return len(keys)

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        numerator = sum(a * b for a, b in zip(left, right, strict=False))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)
