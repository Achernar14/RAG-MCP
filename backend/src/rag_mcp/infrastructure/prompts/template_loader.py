"""Prompt template loading helpers."""

from __future__ import annotations

from pathlib import Path

from rag_mcp.core.exceptions import ConfigurationError
from rag_mcp.core.settings import resolve_project_path


class FilePromptTemplateLoader:
    """Load text prompt templates from project-relative files."""

    def load(self, path: str) -> str:
        """Return the UTF-8 prompt template content."""
        resolved_path = resolve_project_path(path)
        if not resolved_path.exists():
            raise ConfigurationError(f"Prompt template not found: {resolved_path}")
        return resolved_path.read_text(encoding="utf-8").strip()


class StaticPromptTemplateLoader:
    """Small test helper for deterministic prompt template loading."""

    def __init__(self, templates: dict[str, str]) -> None:
        self.templates = dict(templates)

    def load(self, path: str) -> str:
        """Return a pre-registered template body."""
        if path not in self.templates:
            raise ConfigurationError(f"Prompt template not found: {path}")
        return self.templates[path]

