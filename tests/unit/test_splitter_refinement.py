from rag_mcp.domain.entities.models import Document
from rag_mcp.infrastructure.splitters.simple_splitter import SimpleTextSplitter


def _make_document(content: str) -> Document:
    return Document(
        id="doc-1",
        source_path="sample.md",
        filename="sample.md",
        doc_type="md",
        content=content,
        metadata={},
    )


def test_splitter_normalizes_whitespace_and_preserves_paragraph_breaks():
    splitter = SimpleTextSplitter(
        chunk_size=120,
        chunk_overlap=20,
        normalize_whitespace=True,
        preserve_paragraph_breaks=True,
        boundary_scan_chars=40,
        min_chunk_length=10,
    )
    document = _make_document("line one   with   spaces\n\n\nline two\twith tab")

    chunks = splitter.split(document)

    assert chunks
    assert "  " not in chunks[0].text
    assert "\t" not in chunks[0].text
    assert "\n\n\n" not in document.content
    assert "\n\n" in document.content


def test_splitter_prefers_sentence_or_whitespace_boundary():
    splitter = SimpleTextSplitter(
        chunk_size=55,
        chunk_overlap=10,
        normalize_whitespace=True,
        preserve_paragraph_breaks=True,
        boundary_scan_chars=30,
        min_chunk_length=10,
    )
    content = (
        "This is the first sentence. "
        "This is the second sentence with enough words to force another chunk. "
        "Final sentence here."
    )
    document = _make_document(content)

    chunks = splitter.split(document)

    assert len(chunks) >= 2
    assert not chunks[0].text.endswith("sent")
    assert chunks[0].text.endswith("sentence")
    assert "sentence with enough" in chunks[1].text


def test_splitter_filters_tiny_chunks():
    splitter = SimpleTextSplitter(
        chunk_size=30,
        chunk_overlap=5,
        normalize_whitespace=True,
        preserve_paragraph_breaks=False,
        boundary_scan_chars=10,
        min_chunk_length=20,
    )
    document = _make_document("A sufficiently long opening section. tiny")

    chunks = splitter.split(document)

    assert chunks
    assert all(len(chunk.text) >= 20 for chunk in chunks)
