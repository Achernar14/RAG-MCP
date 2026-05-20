"""Chroma-backed vector store implementation."""

from __future__ import annotations

import time

import chromadb

from rag_mcp.domain.entities.models import ChunkRecord, RetrievalResult


class ChromaVectorStore:
    """Persist embeddings and metadata in Chroma."""

    def __init__(
        self,
        persist_path: str,
        collection_name: str,
        max_retries: int = 5,
        retry_delay_seconds: float = 0.2,
    ) -> None:
        self.persist_path = persist_path
        self.collection_name = collection_name
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.client = self._with_lock_retry(
            lambda: chromadb.PersistentClient(path=persist_path)
        )
        self.collection = self._with_lock_retry(
            lambda: self.client.get_or_create_collection(name=collection_name)
        )

    def upsert(self, records: list[ChunkRecord]) -> None:
        """Insert or update records in the collection."""
        if not records:
            return
        self._with_lock_retry(
            lambda: self.collection.upsert(
                ids=[record.id for record in records],
                documents=[record.text for record in records],
                embeddings=[record.dense_vector for record in records],
                metadatas=[self._sanitize_metadata(record.metadata) for record in records],
            )
        )

    def query(self, query_vector: list[float], top_k: int) -> list[RetrievalResult]:
        """Run a nearest-neighbor search."""
        result = self._with_lock_retry(
            lambda: self.collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
            )
        )
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        hits: list[RetrievalResult] = []
        for chunk_id, text, metadata, distance in zip(
            ids,
            documents,
            metadatas,
            distances,
            strict=False,
        ):
            hits.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    score=self._distance_to_score(distance),
                    text=text or "",
                    metadata=metadata or {},
                )
            )
        return hits

    def delete_by_document(self, document_id: str) -> int:
        """Delete all vectors for the specified document."""
        result = self._with_lock_retry(
            lambda: self.collection.get(
                where={"document_id": document_id},
                include=[],
            )
        )
        ids = result.get("ids", []) if result else []
        if not ids:
            return 0
        self._with_lock_retry(lambda: self.collection.delete(ids=ids))
        return len(ids)

    def _sanitize_metadata(self, metadata: dict) -> dict:
        """Convert metadata values to Chroma-compatible primitives."""
        sanitized: dict[str, str | int | float | bool] = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool)):
                sanitized[key] = value
            else:
                sanitized[key] = str(value)
        return sanitized

    def _distance_to_score(self, distance: float | None) -> float:
        """Convert a Chroma distance to a descending similarity-like score."""
        if distance is None:
            return 0.0
        return 1.0 / (1.0 + max(distance, 0.0))

    def close(self) -> None:
        """Release client resources."""
        close_method = getattr(self.client, "close", None)
        if callable(close_method):
            close_method()

    def _with_lock_retry(self, operation):
        """Retry Chroma operations when SQLite reports a transient lock."""
        attempts = 0
        while True:
            try:
                return operation()
            except Exception as exc:
                attempts += 1
                if attempts >= self.max_retries or not self._is_lock_error(exc):
                    raise
                time.sleep(self.retry_delay_seconds)

    def _is_lock_error(self, exc: Exception) -> bool:
        """Return True when the exception is a transient database lock."""
        return "database is locked" in str(exc).lower()
