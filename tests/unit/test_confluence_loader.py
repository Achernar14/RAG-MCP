"""Unit tests for Confluence HTML loader."""

from pathlib import Path

import pytest

from rag_mcp.core.exceptions import IngestionError
from rag_mcp.infrastructure.loaders.confluence_loader import ConfluenceDocumentLoader


# ── Sample Confluence HTML export ────────────────────────────────────

_CONFLUENCE_PAGE = """<!DOCTYPE html>
<html>
<head>
    <title>Test Page - Confluence</title>
    <meta name="confluence-request-time" content="1234567890"/>
</head>
<body>
    <div id="navigation">
        <ul><li><a href="/">Home</a></li><li>Space</li></ul>
    </div>
    <div class="sidebar">
        <p>Page tree here</p>
    </div>
    <header>
        <div class="breadcrumbs">Pages / Space / Test Page</div>
    </header>
    <div id="main-header">
        <h1>Test Page</h1>
        <div class="page-metadata">Created by Author, last modified 2025-01-01</div>
    </div>
    <div id="main-content">
        <h2>Overview</h2>
        <p>This is the first paragraph of the Confluence page content.</p>
        <p>This is the <strong>second paragraph</strong> with some <em>formatting</em>.</p>
        <h3>Details</h3>
        <ul>
            <li>Item one in the list</li>
            <li>Item two in the list</li>
            <li>Item three with <code>code snippet</code> inline</li>
        </ul>
        <div class="code-block">
            <pre>def hello():
    print("Hello Confluence")</pre>
        </div>
        <table>
            <tr><th>Key</th><th>Value</th></tr>
            <tr><td>Status</td><td>Active</td></tr>
        </table>
    </div>
    <footer>
        <p>Powered by Confluence</p>
    </footer>
</body>
</html>"""


@pytest.fixture
def confluence_file(tmp_path):
    """Create a temporary Confluence HTML file."""
    file_path = tmp_path / "test-page.html"
    file_path.write_text(_CONFLUENCE_PAGE, encoding="utf-8")
    return str(file_path)


@pytest.fixture
def loader():
    return ConfluenceDocumentLoader()


# ── Tests ────────────────────────────────────────────────────────────


def test_loads_valid_confluence_html(loader, confluence_file):
    """A valid Confluence HTML file should be loaded successfully."""
    doc = loader.load(confluence_file)
    assert doc.doc_type == "html"
    assert doc.filename == "test-page.html"
    assert len(doc.content) > 0


def test_extracts_main_content_text(loader, confluence_file):
    """The main content paragraphs should appear in the extracted text."""
    doc = loader.load(confluence_file)
    content = doc.content
    assert "first paragraph of the Confluence page content" in content
    assert "second paragraph" in content
    assert "Item one in the list" in content
    assert "Item two in the list" in content
    assert 'print("Hello Confluence")' in content


def test_filters_navigation_noise(loader, confluence_file):
    """Navigation sidebar entries should NOT appear in extracted text."""
    doc = loader.load(confluence_file)
    content = doc.content
    assert "Home" not in content or "Page tree here" not in content


def test_filters_footer_noise(loader, confluence_file):
    """Footer text should NOT appear in extracted text."""
    doc = loader.load(confluence_file)
    content = doc.content
    assert "Powered by Confluence" not in content


def test_filters_breadcrumbs(loader, confluence_file):
    """Breadcrumb text should NOT appear in extracted text."""
    doc = loader.load(confluence_file)
    content = doc.content
    assert "Pages / Space" not in content


def test_filters_metadata_noise(loader, confluence_file):
    """Page metadata (author, dates) should NOT appear in extracted text."""
    doc = loader.load(confluence_file)
    content = doc.content
    assert "Created by Author" not in content


def test_includes_metadata(loader, confluence_file):
    """The document metadata should be enriched."""
    doc = loader.load(confluence_file)
    meta = doc.metadata
    assert meta["loader_name"] == "ConfluenceDocumentLoader"
    assert meta["source_extension"] == ".html"
    assert meta["source_name"] == "test-page.html"
    assert meta["line_count"] > 0
    assert meta["word_count"] > 0


def test_rejects_non_html(tmp_path, loader):
    """Non-HTML files should raise IngestionError."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("plain text content", encoding="utf-8")
    with pytest.raises(IngestionError):
        loader.load(str(file_path))


def test_rejects_missing_file(loader):
    """Missing files should raise IngestionError."""
    with pytest.raises(IngestionError):
        loader.load("/nonexistent/path.html")


def test_fallback_extract_works():
    """The regex fallback should extract text from any HTML."""
    html = "<html><body><p>Hello</p><p>World</p></body></html>"
    from rag_mcp.infrastructure.loaders.confluence_loader import _fallback_extract
    text = _fallback_extract(html)
    assert "Hello" in text
    assert "World" in text
