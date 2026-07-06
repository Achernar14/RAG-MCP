"""Simple text-based document loader."""

from __future__ import annotations

import hashlib
from pathlib import Path

from rag_mcp.core.exceptions import IngestionError
from rag_mcp.domain.entities.models import Document
from rag_mcp.infrastructure.loaders.file_metadata import build_file_metadata


class TextDocumentLoader:
    """Load plain text and markdown documents."""

    def load(self, file_path: str) -> Document:
        """Load a document from disk."""
        path = Path(file_path)
        if not path.exists():
            raise IngestionError(f"File not found: {file_path}")

        suffix = path.suffix.lower()
        if suffix not in {".txt", ".md"}:
            raise IngestionError(f"Unsupported file type: {suffix}")

        file_bytes = path.read_bytes()
        content = file_bytes.decode("utf-8")
        source_fingerprint = hashlib.sha256(file_bytes).hexdigest()
        document_id = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()
        return Document(
            id=document_id,
            source_path=str(path.resolve()),
            filename=path.name,
            doc_type=suffix.lstrip("."),
            content=content,
            metadata=build_file_metadata(
                path,
                content=content,
                source_bytes_fingerprint=source_fingerprint,
                loader_name=self.__class__.__name__,
            ),
        )
