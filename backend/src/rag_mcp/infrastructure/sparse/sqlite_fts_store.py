"""SQLite FTS5-backed sparse retrieval index with BM25 scoring."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import jieba

from rag_mcp.domain.entities.models import ChunkRecord, RetrievalResult

logger = logging.getLogger(__name__)

# FTS5 special characters that must be escaped in MATCH queries.
_FTS5_SPECIAL = str.maketrans({c: f"\"{c}\"" for c in r'*"(){}[]^~:.'''})


def _escape_fts5(text: str) -> str:
    """Escape FTS5 special characters in query text."""
    return text.translate(_FTS5_SPECIAL)


def _tokenize(text: str) -> str:
    """Tokenize text with jieba and join with spaces for FTS5 indexing."""
    tokens = [t.strip() for t in jieba.cut(text) if len(t.strip()) > 1]
    return " ".join(tokens)


class SqliteFtsStore:
    """Persist and query chunk text using SQLite FTS5 with BM25 scoring.

    Chinese text is tokenized with jieba before indexing and querying so
    that FTS5's unicode61 tokenizer receives word-level tokens instead of
    individual CJK characters.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS bm25 "
            "USING fts5(chunk_id, document_id, text, metadata, tokenize='unicode61')"
        )

    # -- public API --------------------------------------------------------

    def upsert(self, records: list[ChunkRecord]) -> None:
        """Insert or replace chunk entries in the FTS5 index."""
        if not records:
            return
        with self.conn:
            for r in records:
                self.conn.execute(
                    "DELETE FROM bm25 WHERE chunk_id = ?", (r.id,)
                )
                self.conn.execute(
                    "INSERT INTO bm25(chunk_id, document_id, text, metadata) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        r.id,
                        r.document_id,
                        _tokenize(r.text),
                        json.dumps(r.metadata, ensure_ascii=False),
                    ),
                )

    def query(self, query_text: str, top_k: int) -> list[RetrievalResult]:
        """Return sparse matches ranked by BM25 score."""
        if not query_text.strip():
            return []

        tokenized = _tokenize(query_text)
        if not tokenized:
            return []

        try:
            rows = self.conn.execute(
                "SELECT chunk_id, text, metadata, bm25(bm25) AS score "
                "FROM bm25 WHERE bm25 MATCH ? ORDER BY score LIMIT ?",
                (_escape_fts5(tokenized), top_k),
            ).fetchall()
        except sqlite3.OperationalError:
            # FTS5 may raise on malformed queries (e.g. only special chars
            # after escaping).  Return empty results gracefully.
            return []

        if not rows:
            return []

        results: list[RetrievalResult] = []
        for row in rows:
            metadata = {}
            try:
                metadata = json.loads(row[2]) if row[2] else {}
            except json.JSONDecodeError:
                pass
            results.append(
                RetrievalResult(
                    chunk_id=row[0],
                    score=1.0 / (1.0 + abs(row[3])),
                    text=row[1] or "",
                    metadata=metadata,
                    retrieval_method="sparse",
                )
            )
        return results[:top_k]

    def delete_by_document(self, document_id: str) -> int:
        """Delete all FTS5 entries for a document. Returns deleted count."""
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM bm25 WHERE document_id = ?", (document_id,)
        )
        count = cursor.fetchone()[0]
        if count:
            with self.conn:
                self.conn.execute(
                    "DELETE FROM bm25 WHERE document_id = ?", (document_id,)
                )
        return count

    def exists(self) -> bool:
        """Return True when the FTS5 index contains at least one entry."""
        row = self.conn.execute("SELECT COUNT(*) FROM bm25").fetchone()
        return row is not None and row[0] > 0

    def close(self) -> None:
        """Close the SQLite connection."""
        try:
            self.conn.close()
        except Exception:
            logger.debug("SQLite connection close failed", exc_info=True)
