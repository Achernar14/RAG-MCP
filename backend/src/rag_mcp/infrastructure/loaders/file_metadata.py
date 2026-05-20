"""Shared file metadata enrichment helpers for ingestion."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sha256_hex(raw: bytes) -> str:
    """Return a hex SHA-256 digest for raw bytes."""
    return hashlib.sha256(raw).hexdigest()


def build_file_metadata(
    path: Path,
    *,
    content: str,
    file_bytes: bytes,
    loader_name: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build enriched ingestion metadata for a local file."""
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
        "source_bytes_fingerprint": _sha256_hex(file_bytes),
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
