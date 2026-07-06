"""Confluence HTML export loader.

Parses Confluence-exported HTML pages, extracting the main content
while filtering out navigation, sidebar, header, and footer noise.
"""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path

from rag_mcp.core.exceptions import IngestionError
from rag_mcp.domain.entities.models import Document
from rag_mcp.infrastructure.loaders.file_metadata import build_file_metadata


# ------------------------------------------------------------------
# Content extraction selectors (tried in order)
# ------------------------------------------------------------------
_CONTENT_SELECTORS: list[tuple[str, str]] = [
    # (tag, class_or_id_attr) — we match tag + optional class/id
    ("div", "wiki-content"),
    ("div", "page-content"),
    ("div", "content"),
    ("main", ""),
    ("article", ""),
    ("body", ""),  # fallback — use entire body
]

# Tags whose content is always discarded (navigation, chrome)
_SKIP_TAGS: set[str] = {
    "nav", "header", "footer", "script", "style", "noscript",
}

# Class/id substrings that mark a container as noise
_SKIP_CLASS_PATTERNS: list[str] = [
    "navigation", "nav", "sidebar", "breadcrumb",
    "header", "footer", "page-metadata", "page-info",
    "toolbar", "menu", "actions", "controls",
]


def _is_noise_node(tag: str, attrs: dict[str, str | None]) -> bool:
    """Return True if the HTML node should be excluded from extraction."""
    if tag in _SKIP_TAGS:
        return True
    cls = (attrs.get("class") or "").lower()
    id_ = (attrs.get("id") or "").lower()
    combined = f"{cls} {id_}"
    for pattern in _SKIP_CLASS_PATTERNS:
        if pattern in combined:
            return True
    return False


# ------------------------------------------------------------------
# Confluence-specific HTML parser
# ------------------------------------------------------------------


class _ConfluenceContentExtractor(HTMLParser):
    """State-machine HTML parser that extracts body text from Confluence HTML.

    Strips all tags and returns only the textual content from the main
    content area (skipping navigation / sidebar / header / footer noise).
    """

    def __init__(self) -> None:
        super().__init__()
        self._content_lines: list[str] = []
        self._current_text: list[str] = []
        self._skip_depth: int = 0
        self._in_content: bool = False
        self._content_tag: str = ""
        self._content_attr_value: str = ""

    # -- public result -------------------------------------------------

    def extracted_text(self) -> str:
        """Return the extracted content as a single string."""
        return "\n".join(self._content_lines).strip()

    # -- parser callbacks -----------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)

        if self._skip_depth > 0:
            if self._is_self_closing(tag):
                return
            self._skip_depth += 1
            return

        # Check if this tag starts the content area
        if not self._in_content:
            if self._matches_content_selector(tag, attrs_dict):
                self._in_content = True
                self._content_tag = tag
                cls = attrs_dict.get("class") or ""
                id_ = attrs_dict.get("id") or ""
                self._content_attr_value = f"{cls} {id_}".strip()
                return

        # Check if this tag is noise
        if _is_noise_node(tag, attrs_dict):
            if not self._is_self_closing(tag):
                self._skip_depth = 1
            return

        # Block-level elements → insert paragraph break
        if self._in_content:
            self._flush_text()
            if tag in {"p", "br", "div", "section", "article",
                        "h1", "h2", "h3", "h4", "h5", "h6",
                        "li", "tr", "blockquote", "pre", "hr", "table"}:
                self._content_lines.append("")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth > 0:
            if tag == self._content_tag and self._in_content:
                # Shouldn't typically happen (content div usually contains everything)
                pass
            self._skip_depth -= 1
            return

        # Flush accumulated inline text
        self._flush_text()

        # End of content area?
        if self._in_content and tag == self._content_tag:
            self._in_content = False

        # Block-level endings → paragraph break
        if tag in {"p", "div", "section", "article",
                    "h1", "h2", "h3", "h4", "h5", "h6",
                    "li", "blockquote", "pre", "tr"}:
            self._content_lines.append("")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = data.strip()
        if text:
            self._current_text.append(text)

    # -- helpers -------------------------------------------------------

    def _flush_text(self) -> None:
        """Accumulate inline text into a content line."""
        if self._current_text:
            self._content_lines.append(" ".join(self._current_text))
            self._current_text.clear()

    def _matches_content_selector(
        self, tag: str, attrs: dict[str, str | None]
    ) -> bool:
        """Return True if *tag* + *attrs* matches a known content selector."""
        for sel_tag, sel_value in _CONTENT_SELECTORS:
            if tag != sel_tag:
                continue
            if not sel_value:
                return True
            cls = (attrs.get("class") or "").lower()
            id_ = (attrs.get("id") or "").lower()
            if sel_value in cls or sel_value in id_:
                return True
        return False

    @staticmethod
    def _is_self_closing(tag: str) -> bool:
        """Return True for void/self-closing HTML elements."""
        return tag in {
            "br", "hr", "img", "input", "meta", "link",
            "area", "base", "col", "embed", "source", "track", "wbr",
        }


# ------------------------------------------------------------------
# Public loader class
# ------------------------------------------------------------------


class ConfluenceDocumentLoader:
    """Load a Confluence-exported HTML page.

    Extracts the main content area, drops navigation/sidebar/header/footer
    noise, and returns a clean :class:`Document` suitable for chunking and
    indexing.
    """

    def load(self, file_path: str) -> Document:
        """Parse a Confluence HTML file and extract clean body text."""
        path = Path(file_path)
        if not path.exists():
            raise IngestionError(f"File not found: {file_path}")
        if path.suffix.lower() not in {".html", ".htm"}:
            raise IngestionError(
                f"ConfluenceDocumentLoader expects .html/.htm files, got: {path.suffix}"
            )

        file_bytes = path.read_bytes()
        raw_html = file_bytes.decode("utf-8", errors="replace")

        # Extract body text
        content = self._extract_content(raw_html)
        if not content:
            raise IngestionError(
                f"No extractable content found in Confluence HTML: {file_path}"
            )

        # Normalise whitespace
        content = self._normalise(content)

        document_id = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()
        return Document(
            id=document_id,
            source_path=str(path.resolve()),
            filename=path.name,
            doc_type="html",
            content=content,
            metadata=build_file_metadata(
                path,
                content=content,
                file_bytes=file_bytes,
                loader_name=self.__class__.__name__,
            ),
        )

    # -- internal helpers ------------------------------------------------

    @staticmethod
    def _extract_content(raw_html: str) -> str:
        """Extract body text from Confluence HTML using the custom parser."""
        parser = _ConfluenceContentExtractor()
        try:
            parser.feed(raw_html)
        except Exception:
            # Fall back to regex-based extraction on parse errors
            return _fallback_extract(raw_html)
        text = parser.extracted_text()
        if not text:
            text = _fallback_extract(raw_html)
        return text

    @staticmethod
    def _normalise(content: str) -> str:
        """Collapse blank lines and normalise whitespace."""
        # Collapse 3+ consecutive newlines into 2
        content = re.sub(r"\n{3,}", "\n\n", content)
        # Strip leading/trailing whitespace per line
        content = "\n".join(line.strip() for line in content.splitlines())
        return content.strip()


def _fallback_extract(raw_html: str) -> str:
    """Regex-based fallback: strip all tags and return remaining text."""
    # Remove script/style blocks
    cleaned = re.sub(
        r"<(script|style|nav|header|footer|noscript)[^>]*>.*?</\1>",
        "",
        raw_html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Remove all remaining tags
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    # Decode common HTML entities
    cleaned = cleaned.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    cleaned = cleaned.replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'")
    # Collapse whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
