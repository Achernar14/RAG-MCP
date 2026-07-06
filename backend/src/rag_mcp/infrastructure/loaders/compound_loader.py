"""Dispatcher loader that selects a concrete loader by file extension."""

from __future__ import annotations

from pathlib import Path

from rag_mcp.core.exceptions import IngestionError


class CompoundDocumentLoader:
    """Route loading to the correct concrete loader."""

    def __init__(self, text_loader, pdf_loader, confluence_loader=None) -> None:
        self.text_loader = text_loader
        self.pdf_loader = pdf_loader
        self.confluence_loader = confluence_loader

    def load(self, file_path: str):
        """Load a file using an extension-aware strategy."""
        suffix = Path(file_path).suffix.lower()
        if suffix in {".txt", ".md"}:
            return self.text_loader.load(file_path)
        if suffix == ".pdf":
            return self.pdf_loader.load(file_path)
        if suffix in {".html", ".htm"} and self.confluence_loader is not None:
            return self.confluence_loader.load(file_path)
        raise IngestionError(f"Unsupported file type: {suffix}")

