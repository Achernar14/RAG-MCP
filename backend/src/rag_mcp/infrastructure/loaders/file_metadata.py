"""Shared file metadata enrichment helpers for ingestion."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Chunk size for streaming file reads \u2014 small enough to keep memory flat,
# large enough to amortize I/O overhead across the chunk.
_STREAMING_CHUNK_SIZE = 64 * 1024  # 64 KiB


def streaming_file_sha256(path: Path, chunk_size: int = _STREAMING_CHUNK_SIZE) -> str:
    """Compute the SHA-256 hex digest of *path* without loading the entire
    file into memory.

    Reads the file in *chunk_size* blocks (default 64 KiB) so that peak
    memory is bounded by the chunk size rather than the file size.
    """
    hasher = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _sha256_hex(raw: bytes) -> str:
    """Return a hex SHA-256 digest for raw bytes."""
    return hashlib.sha256(raw).hexdigest()


def build_file_metadata(
    path: Path,
    *,
    content: str,
    source_bytes_fingerprint: str,
    loader_name: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build enriched ingestion metadata for a local file.

    Args:
        path: The file path on disk.
        content: Extracted text content.
        source_bytes_fingerprint: SHA-256 hex digest of the raw file bytes
            (computed via :func:`streaming_file_sha256` for large files, or
            ``hashlib.sha256(file_bytes).hexdigest()`` when the bytes are
            already in memory).
        loader_name: Class name of the loader.
        extra: Optional dictionary merged into the metadata.
    """
    stat = path.stat()
    non_empty_char_count = len("".join(content.split()))
    word_count = len(content.split())
    contains_cjk = any("\u4e00" <= char <= "\u9fff" for char in content)
    metadata: dict[str, Any] = {
        "source_path": str(path.resolve()),
        "source_name": path.name,
        "source_extension": path.suffix.lower(),
        "source_size_bytes": stat.st_size,
        "source_modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "source_modified_at_ns": stat.st_mtime_ns,
        "source_bytes_fingerprint": source_bytes_fingerprint,
        "content_fingerprint": _sha256_hex(content.encode("utf-8")),
        "content_length": len(content),
        "line_count": len(content.splitlines()),
        "word_count": word_count,
        "non_empty_char_count": non_empty_char_count,
        "contains_cjk": contains_cjk,
        "loader_name": loader_name,
        "metadata_version": 1,
    }
    if extra:
        metadata.update(extra)
    return metadata
