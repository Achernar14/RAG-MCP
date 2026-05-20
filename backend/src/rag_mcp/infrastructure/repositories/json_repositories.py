"""JSON-backed repositories for persistent local metadata."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from rag_mcp.domain.entities.models import Chunk, Document


def _serialize_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported type: {type(value)!r}")


class JsonDocumentRepository:
    """Persist documents to a JSON file."""

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.documents: dict[str, Document] = {}
        self._load()

    def save(self, document: Document) -> None:
        self.documents[document.id] = document
        self._flush()

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
        self._flush()
        return True

    def _load(self) -> None:
        if not self.file_path.exists():
            return
        raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        for item in raw:
            self.documents[item["id"]] = Document(
                id=item["id"],
                source_path=item["source_path"],
                filename=item["filename"],
                doc_type=item["doc_type"],
                content=item["content"],
                metadata=item.get("metadata", {}),
                created_at=datetime.fromisoformat(item["created_at"]),
                updated_at=datetime.fromisoformat(item["updated_at"]),
            )

    def _flush(self) -> None:
        payload = [asdict(document) for document in self.documents.values()]
        self.file_path.write_text(
            json.dumps(payload, ensure_ascii=False, default=_serialize_datetime, indent=2),
            encoding="utf-8",
        )


class JsonChunkRepository:
    """Persist chunks to a JSON file."""

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.chunks_by_document: dict[str, list[Chunk]] = {}
        self._load()

    def save_many(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        self.chunks_by_document[chunks[0].document_id] = list(chunks)
        self._flush()

    def list_by_document(self, document_id: str) -> list[Chunk]:
        return list(self.chunks_by_document.get(document_id, []))

    def delete_by_document(self, document_id: str) -> int:
        chunks = self.chunks_by_document.pop(document_id, [])
        if chunks:
            self._flush()
        return len(chunks)

    def _load(self) -> None:
        if not self.file_path.exists():
            return
        raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        for document_id, items in raw.items():
            self.chunks_by_document[document_id] = [
                Chunk(
                    id=item["id"],
                    document_id=item["document_id"],
                    text=item["text"],
                    chunk_index=item["chunk_index"],
                    start_offset=item["start_offset"],
                    end_offset=item["end_offset"],
                    metadata=item.get("metadata", {}),
                )
                for item in items
            ]

    def _flush(self) -> None:
        payload = {
            document_id: [asdict(chunk) for chunk in chunks]
            for document_id, chunks in self.chunks_by_document.items()
        }
        self.file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
