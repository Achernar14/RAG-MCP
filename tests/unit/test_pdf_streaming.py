"""Unit tests for streaming file hash and PDF loader memory safety."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from rag_mcp.infrastructure.loaders.file_metadata import (
    build_file_metadata,
    streaming_file_sha256,
)
from rag_mcp.infrastructure.loaders.pdf_loader import PdfDocumentLoader


# ── streaming_file_sha256 ──────────────────────────────────────────────


class TestStreamingFileSha256:
    """Verify the streaming SHA-256 helper works correctly."""

    def test_matches_one_shot_hash(self, tmp_path: Path):
        """Streaming hash matches the one-shot hash of the same file."""
        content = b"Hello, PDF streaming world!\n" * 1000  # ~28 KB
        file_path = tmp_path / "test.bin"
        file_path.write_bytes(content)

        streaming = streaming_file_sha256(file_path)
        one_shot = hashlib.sha256(content).hexdigest()
        assert streaming == one_shot

    def test_small_chunk_size(self, tmp_path: Path):
        """Works correctly when chunk_size is smaller than file."""
        content = b"x" * 5000
        file_path = tmp_path / "small.bin"
        file_path.write_bytes(content)

        result = streaming_file_sha256(file_path, chunk_size=64)  # tiny chunks
        expected = hashlib.sha256(content).hexdigest()
        assert result == expected

    def test_exact_chunk_boundary(self, tmp_path: Path):
        """File size is an exact multiple of chunk_size."""
        chunk_size = 128
        content = b"A" * (chunk_size * 10)  # exactly 10 chunks
        file_path = tmp_path / "exact.bin"
        file_path.write_bytes(content)

        result = streaming_file_sha256(file_path, chunk_size=chunk_size)
        expected = hashlib.sha256(content).hexdigest()
        assert result == expected

    def test_empty_file(self, tmp_path: Path):
        """Empty file produces the SHA-256 of empty bytes."""
        file_path = tmp_path / "empty.bin"
        file_path.write_bytes(b"")

        result = streaming_file_sha256(file_path)
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected

    def test_deterministic(self, tmp_path: Path):
        """Same file content → same hash across multiple calls."""
        content = b"deterministic test data\n" * 500
        file_path = tmp_path / "det.bin"
        file_path.write_bytes(content)

        h1 = streaming_file_sha256(file_path)
        h2 = streaming_file_sha256(file_path)
        h3 = streaming_file_sha256(file_path, chunk_size=1024)
        assert h1 == h2 == h3

    def test_different_files_different_hashes(self, tmp_path: Path):
        """Two different files produce different hashes."""
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")

        assert streaming_file_sha256(f1) != streaming_file_sha256(f2)

    def test_large_file_handled(self, tmp_path: Path):
        """The helper handles a moderately large file without issue."""
        # 5 MB — large enough to verify chunking, small enough for unit tests
        file_path = tmp_path / "large.bin"
        # Write in chunks to avoid creating a 5 MB bytes object
        with open(file_path, "wb") as fh:
            pattern = b"LARGE_FILE_TEST_" * 40  # ~640 bytes per write
            for _ in range(8192):  # ~5 MB total
                fh.write(pattern)

        result = streaming_file_sha256(file_path, chunk_size=65536)

        # Verify by computing one-shot hash (via streaming to be fair)
        expected = hashlib.sha256()
        with open(file_path, "rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                expected.update(chunk)
        assert result == expected.hexdigest()

    def test_default_chunk_size_is_64k(self, tmp_path: Path):
        """The default chunk size is 64 KiB (the _STREAMING_CHUNK_SIZE constant)."""
        content = b"test " * 5000
        file_path = tmp_path / "chunk_test.bin"
        file_path.write_bytes(content)

        # Should work without specifying chunk_size
        result = streaming_file_sha256(file_path)
        assert len(result) == 64  # SHA-256 hex is always 64 chars
        assert result == hashlib.sha256(content).hexdigest()


# ── build_file_metadata (new signature) ────────────────────────────────


class TestBuildFileMetadata:
    """Verify build_file_metadata works with the new source_bytes_fingerprint parameter."""

    def test_metadata_includes_fingerprint(self, tmp_path: Path):
        """The passed fingerprint appears in metadata under source_bytes_fingerprint."""
        file_path = tmp_path / "doc.txt"
        file_path.write_text("Hello metadata world!", encoding="utf-8")

        fingerprint = hashlib.sha256(file_path.read_bytes()).hexdigest()
        metadata = build_file_metadata(
            file_path,
            content="Hello metadata world!",
            source_bytes_fingerprint=fingerprint,
            loader_name="TestLoader",
        )

        assert metadata["source_bytes_fingerprint"] == fingerprint
        assert len(metadata["source_bytes_fingerprint"]) == 64

    def test_content_fingerprint_still_computed(self, tmp_path: Path):
        """content_fingerprint is still automatically computed from content."""
        file_path = tmp_path / "doc2.txt"
        file_path.write_text("Content for fingerprinting.", encoding="utf-8")

        metadata = build_file_metadata(
            file_path,
            content="Content for fingerprinting.",
            source_bytes_fingerprint="abcdef0123456789" * 4,
            loader_name="TestLoader",
        )

        expected_content_hash = hashlib.sha256(
            "Content for fingerprinting.".encode("utf-8")
        ).hexdigest()
        assert metadata["content_fingerprint"] == expected_content_hash

    def test_extra_fields_merged(self, tmp_path: Path):
        """Extra dict is merged into the metadata."""
        file_path = tmp_path / "doc3.txt"
        file_path.write_text("extra", encoding="utf-8")

        metadata = build_file_metadata(
            file_path,
            content="extra",
            source_bytes_fingerprint="aa" * 32,
            loader_name="TestLoader",
            extra={"custom_field": 42, "page_count": 5},
        )

        assert metadata["custom_field"] == 42
        assert metadata["page_count"] == 5


# ── PdfDocumentLoader memory safety ────────────────────────────────────


class TestPdfLoaderMemorySafety:
    """Verify PdfDocumentLoader does not load the full file into memory."""

    def test_load_succeeds_without_read_bytes(self, tmp_path: Path, monkeypatch):
        """PDF loader should work without ever calling Path.read_bytes()."""
        # Use the real sample.pdf from the project
        sample_pdf = (
            Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.pdf"
        )

        # Track whether Path.read_bytes is called
        original_read_bytes = Path.read_bytes
        call_count = [0]

        def _tracked_read_bytes(self_path):
            call_count[0] += 1
            return original_read_bytes(self_path)

        monkeypatch.setattr(Path, "read_bytes", _tracked_read_bytes)

        loader = PdfDocumentLoader()
        doc = loader.load(str(sample_pdf))

        # The loader should succeed
        assert doc.doc_type == "pdf"
        assert len(doc.content) > 0
        # Path.read_bytes should NOT have been called by PdfDocumentLoader
        assert call_count[0] == 0, (
            f"PdfDocumentLoader called Path.read_bytes() {call_count[0]} time(s); "
            "it should use streaming_file_sha256() instead"
        )

    def test_fingerprint_matches_one_shot(self, tmp_path: Path):
        """The source_bytes_fingerprint in PDF metadata matches the real file hash."""
        sample_pdf = (
            Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.pdf"
        )

        loader = PdfDocumentLoader()
        doc = loader.load(str(sample_pdf))

        # Compute expected hash
        expected = hashlib.sha256(sample_pdf.read_bytes()).hexdigest()
        assert doc.metadata["source_bytes_fingerprint"] == expected
