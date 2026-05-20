"""Local file inspection helpers for ingestion pre-checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rag_mcp.core.exceptions import IngestionError


@dataclass(frozen=True)
class SourceInspection:
    """Cheap pre-load inspection result for a local source file."""

    path: str
    name: str
    extension: str
    size_bytes: int
    modified_at_ns: int
    bytes_fingerprint: str


class LocalSourceInspector:
    """Inspect local files before full document loading."""

    def inspect(self, file_path: str) -> SourceInspection:
        """Collect cheap file metadata and a byte-level fingerprint."""
        path = Path(file_path)
        if not path.exists():
            raise IngestionError(f"File not found: {file_path}")
        if not path.is_file():
            raise IngestionError(f"Path is not a file: {file_path}")

        raw = path.read_bytes()
        stat = path.stat()
        return SourceInspection(
            path=str(path.resolve()),
            name=path.name,
            extension=path.suffix.lower(),
            size_bytes=stat.st_size,
            modified_at_ns=stat.st_mtime_ns,
            bytes_fingerprint=self._sha256_hex(raw),
        )

    def _sha256_hex(self, raw: bytes) -> str:
        import hashlib

        return hashlib.sha256(raw).hexdigest()
