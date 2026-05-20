"""A lightweight BM25-style sparse index persisted as JSON."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from rag_mcp.domain.entities.models import ChunkRecord, RetrievalResult


TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


class JsonBm25Store:
    """Persist and query a simple BM25 sparse index."""

    def __init__(self, index_path: str | Path) -> None:
        self.index_path = Path(index_path)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.documents: dict[str, dict] = {}
        self._load()

    def upsert(self, records: list[ChunkRecord]) -> None:
        """Insert or replace chunk entries in the sparse index."""
        for record in records:
            terms = self._tokenize(record.text)
            frequencies = Counter(terms)
            self.documents[record.id] = {
                "chunk_id": record.id,
                "document_id": record.document_id,
                "text": record.text,
                "metadata": record.metadata,
                "term_frequencies": dict(frequencies),
                "doc_length": len(terms),
            }
        self._flush()

    def query(self, query_text: str, top_k: int) -> list[RetrievalResult]:
        """Return sparse matches ranked by a BM25-style score."""
        query_terms = self._tokenize(query_text)
        if not query_terms or not self.documents:
            return []

        document_count = len(self.documents)
        average_length = sum(doc["doc_length"] for doc in self.documents.values()) / max(
            document_count, 1
        )
        scores: list[tuple[float, dict]] = []
        for document in self.documents.values():
            score = 0.0
            for term in query_terms:
                df = sum(
                    1 for item in self.documents.values() if term in item["term_frequencies"]
                )
                if df == 0:
                    continue
                tf = document["term_frequencies"].get(term, 0)
                if tf == 0:
                    continue
                idf = math.log(1 + (document_count - df + 0.5) / (df + 0.5))
                k1 = 1.5
                b = 0.75
                denominator = tf + k1 * (
                    1 - b + b * (document["doc_length"] / max(average_length, 1))
                )
                score += idf * ((tf * (k1 + 1)) / max(denominator, 1e-9))
            if score > 0:
                scores.append((score, document))

        scores.sort(key=lambda item: item[0], reverse=True)
        max_score = scores[0][0] if scores else 1.0
        return [
            RetrievalResult(
                chunk_id=document["chunk_id"],
                score=score / max(max_score, 1e-9),
                text=document["text"],
                metadata=document["metadata"],
                retrieval_method="sparse",
            )
            for score, document in scores[:top_k]
        ]

    def exists(self) -> bool:
        """Return True if the sparse index file exists."""
        return self.index_path.exists()

    def delete_by_document(self, document_id: str) -> int:
        """Delete sparse entries for a document."""
        keys = [
            chunk_id
            for chunk_id, payload in self.documents.items()
            if payload.get("document_id") == document_id
        ]
        for key in keys:
            del self.documents[key]
        if keys:
            self._flush()
        return len(keys)

    def _tokenize(self, text: str) -> list[str]:
        return [token.lower() for token in TOKEN_PATTERN.findall(text)]

    def _load(self) -> None:
        if not self.index_path.exists():
            return
        self.documents = json.loads(self.index_path.read_text(encoding="utf-8"))

    def _flush(self) -> None:
        self.index_path.write_text(
            json.dumps(self.documents, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
