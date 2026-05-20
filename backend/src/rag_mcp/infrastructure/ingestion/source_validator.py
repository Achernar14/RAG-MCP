"""Local source validation helpers for ingestion safety checks."""

from __future__ import annotations

from pathlib import Path

from rag_mcp.core.exceptions import SourceValidationError


class LocalSourceValidator:
    """Validate local files before expensive ingestion work begins."""

    def __init__(
        self,
        *,
        supported_extensions: list[str],
        max_file_size_bytes: int,
        allow_hidden_files: bool,
    ) -> None:
        self.supported_extensions = {item.lower() for item in supported_extensions}
        self.max_file_size_bytes = max_file_size_bytes
        self.allow_hidden_files = allow_hidden_files

    def validate(self, file_path: str) -> Path:
        """Validate a local source file and return its resolved path."""
        path = Path(file_path)
        if not path.exists():
            raise SourceValidationError(f"File not found: {file_path}")
        if not path.is_file():
            raise SourceValidationError(f"Path is not a file: {file_path}")
        if not self.allow_hidden_files and path.name.startswith("."):
            raise SourceValidationError(f"Hidden files are not allowed: {file_path}")

        suffix = path.suffix.lower()
        if suffix not in self.supported_extensions:
            raise SourceValidationError(
                f"Unsupported file type: {suffix or '<no extension>'}. "
                f"Supported types: {', '.join(sorted(self.supported_extensions))}"
            )

        size_bytes = path.stat().st_size
        if size_bytes == 0:
            raise SourceValidationError(f"File is empty: {file_path}")
        if size_bytes > self.max_file_size_bytes:
            raise SourceValidationError(
                f"File exceeds max size limit ({self.max_file_size_bytes} bytes): {file_path}"
            )

        return path.resolve()
