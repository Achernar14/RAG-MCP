"""PDF document loader."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pypdf import PdfReader

from rag_mcp.core.exceptions import IngestionError
from rag_mcp.domain.entities.models import Document
from rag_mcp.infrastructure.loaders.file_metadata import build_file_metadata


class PdfDocumentLoader:
    """Load text content from PDF documents."""

    def load(self, file_path: str) -> Document:
        """Extract text from a PDF file."""
        path = Path(file_path)
        if not path.exists():
            raise IngestionError(f"File not found: {file_path}")
        if path.suffix.lower() != ".pdf":
            raise IngestionError(f"Unsupported file type: {path.suffix}")

        file_bytes = path.read_bytes()
        reader = PdfReader(str(path))
        content_parts: list[str] = []
        for page in reader.pages:
            content_parts.append(page.extract_text() or "")
        content = "\n\n".join(content_parts).strip()
        if not content:
            raise IngestionError(f"No extractable text found in PDF: {file_path}")

        image_assets = self._build_multimodal_asset_skeleton(page_count=len(reader.pages))

        document_id = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()
        return Document(
            id=document_id,
            source_path=str(path.resolve()),
            filename=path.name,
            doc_type="pdf",
            content=content,
            metadata=build_file_metadata(
                path,
                content=content,
                file_bytes=file_bytes,
                loader_name=self.__class__.__name__,
                extra={
                    "page_count": len(reader.pages),
                    "assets": image_assets,
                    "multimodal_status": "skeleton_only",
                    "image_asset_count": len(image_assets),
                },
            ),
        )

    def _build_multimodal_asset_skeleton(self, *, page_count: int) -> list[dict]:
        """Return the current multimodal asset skeleton for a PDF document.

        The project does not yet extract embedded images. We still persist a stable
        assets field so later vision/image extraction can evolve without changing
        document contracts again.
        """
        del page_count
        return []
