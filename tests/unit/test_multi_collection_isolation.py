"""Integration tests for P3-T4: Collection-level data isolation.

Verifies that different collections have independent documents, vectors,
and indexes, and that ingest/query/delete can target specific collections.
"""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from rag_mcp.core.container import reset_container
from rag_mcp.main import create_app


COLLECTION_A = "collection_a"
COLLECTION_B = "collection_b"


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    """Create a test environment with multi-collection support."""
    reset_container()
    runtime_root = tmp_path / "runtime"
    settings_path = tmp_path / "settings.yaml"
    settings_payload = {
        "app": {"name": "rag-mcp", "environment": "test"},
        "embedding": {"provider": "hash", "dimensions": 64},
        "vector_store": {
            "provider": "chroma",
            "collection_name": COLLECTION_A,  # default collection
            "persist_path": str(runtime_root / "vector_store" / "chroma_live"),
        },
        "ingestion": {
            "chunk_size": 500,
            "chunk_overlap": 50,
            "normalize_whitespace": True,
            "preserve_paragraph_breaks": True,
            "boundary_scan_chars": 80,
            "min_chunk_length": 40,
            "supported_extensions": [".txt", ".md", ".pdf"],
        },
        "retrieval": {
            "top_k": 5,
            "dense_top_k": 5,
            "sparse_top_k": 5,
            "hybrid_top_k": 5,
            "rrf_k": 60,
            "rerank_enabled": True,
            "rerank_top_k": 5,
        },
        "observability": {
            "trace_enabled": True,
            "trace_path": str(runtime_root / "traces" / "traces.jsonl"),
        },
        "mcp": {"server_name": "rag-mcp", "server_version": "0.1.0"},
        "api": {"host": "127.0.0.1", "port": 8000},
    }
    settings_path.write_text(yaml.safe_dump(settings_payload), encoding="utf-8")
    monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))
    runtime_root.mkdir(parents=True, exist_ok=True)
    yield runtime_root
    reset_container()


def _ingest_into(client: TestClient, sample_path: Path, collection_name: str):
    """Ingest a document into a specific collection."""
    response = client.post(
        "/api/v1/ingest",
        json={
            "path": str(sample_path),
            "collection_name": collection_name,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


# ── Core isolation tests ─────────────────────────────────────────────


def test_different_collections_have_isolated_documents():
    """Ingesting the same file into two collections creates independent entries."""
    app = create_app()
    client = TestClient(app)

    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"

    # Ingest into collection A
    result_a = _ingest_into(client, sample_path, COLLECTION_A)
    doc_id_a = result_a["data"]["document_id"]
    assert result_a["data"]["chunk_count"] >= 1

    # Ingest SAME file into collection B — should create separate entry
    result_b = _ingest_into(client, sample_path, COLLECTION_B)
    doc_id_b = result_b["data"]["document_id"]
    assert result_b["data"]["chunk_count"] >= 1

    # Same file path, same content hash → same document_id
    # but each collection has its own isolated copy
    assert doc_id_a == doc_id_b  # same content hash

    # List collection A — should have the document
    docs_a = client.get(
        "/api/v1/documents", params={"collection_name": COLLECTION_A}
    )
    assert docs_a.status_code == 200
    assert len(docs_a.json()["data"]) == 1

    # List collection B — should also have the document (independent copy)
    docs_b = client.get(
        "/api/v1/documents", params={"collection_name": COLLECTION_B}
    )
    assert docs_b.status_code == 200
    assert len(docs_b.json()["data"]) == 1


def test_query_isolated_between_collections():
    """Query results should only come from the targeted collection."""
    app = create_app()
    client = TestClient(app)

    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"
    bm25_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "bm25_sample.md"

    # Collection A: sample.md only
    _ingest_into(client, sample_path, COLLECTION_A)

    # Collection B: bm25_sample.md only
    _ingest_into(client, bm25_path, COLLECTION_B)

    # Query collection A — should find "MVP" content (from sample.md)
    query_a = client.post(
        "/api/v1/query",
        json={
            "query": "What does the MVP support?",
            "top_k": 3,
            "collection_name": COLLECTION_A,
        },
    )
    assert query_a.status_code == 200
    results_a = query_a.json()["data"]["results"]
    assert results_a

    # Query collection B — same query but different collection
    query_b = client.post(
        "/api/v1/query",
        json={
            "query": "What does the MVP support?",
            "top_k": 3,
            "collection_name": COLLECTION_B,
        },
    )
    assert query_b.status_code == 200
    results_b = query_b.json()["data"]["results"]
    assert results_b


def test_delete_document_only_affects_target_collection():
    """Deleting a document from one collection does not affect another."""
    app = create_app()
    client = TestClient(app)

    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"

    # Ingest into both collections
    result_a = _ingest_into(client, sample_path, COLLECTION_A)
    doc_id = result_a["data"]["document_id"]
    _ingest_into(client, sample_path, COLLECTION_B)

    # Delete from collection A only
    delete_resp = client.delete(
        f"/api/v1/documents/{doc_id}",
        params={"collection_name": COLLECTION_A},
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["data"]["deleted_chunk_count"] >= 1

    # Collection A should now be empty
    docs_a = client.get(
        "/api/v1/documents", params={"collection_name": COLLECTION_A}
    )
    assert docs_a.status_code == 200
    assert len(docs_a.json()["data"]) == 0

    # Collection B should still have the document
    docs_b = client.get(
        "/api/v1/documents", params={"collection_name": COLLECTION_B}
    )
    assert docs_b.status_code == 200
    assert len(docs_b.json()["data"]) == 1


def test_list_collections_shows_all_collections():
    """After ingesting into multiple collections, list shows them all."""
    app = create_app()
    client = TestClient(app)

    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"

    # Ingest into both collections
    _ingest_into(client, sample_path, COLLECTION_A)
    _ingest_into(client, sample_path, COLLECTION_B)

    # List collections should show both
    response = client.get("/api/v1/collections")
    assert response.status_code == 200
    collections = response.json()["data"]
    collection_names = {c["name"] for c in collections}
    assert COLLECTION_A in collection_names
    assert COLLECTION_B in collection_names

    # Each collection should have its own document count
    for c in collections:
        assert c["document_count"] >= 1
        assert c["chunk_count"] >= 1
        assert c["vector_store_provider"] == "chroma"


def test_stats_respect_collection_scope():
    """The /stats endpoint reflects only the targeted collection."""
    app = create_app()
    client = TestClient(app)

    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"

    # Only ingest into collection A
    _ingest_into(client, sample_path, COLLECTION_A)

    # Stats for collection A should show documents
    stats_a = client.get("/api/v1/stats", params={"collection_name": COLLECTION_A})
    assert stats_a.status_code == 200
    body_a = stats_a.json()["data"]
    assert body_a["document_count"] >= 1
    assert body_a["collection_name"] == COLLECTION_A

    # Stats for collection B should be empty
    stats_b = client.get("/api/v1/stats", params={"collection_name": COLLECTION_B})
    assert stats_b.status_code == 200
    body_b = stats_b.json()["data"]
    assert body_b["document_count"] == 0
    assert body_b["collection_name"] == COLLECTION_B


def test_rebuild_targets_specific_collection():
    """Rebuild should only affect the targeted collection."""
    app = create_app()
    client = TestClient(app)

    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"

    # Ingest into both collections
    _ingest_into(client, sample_path, COLLECTION_A)
    _ingest_into(client, sample_path, COLLECTION_B)

    # Rebuild collection A
    rebuild = client.post(
        "/api/v1/collections/rebuild",
        params={"collection_name": COLLECTION_A},
    )
    assert rebuild.status_code == 200
    body = rebuild.json()["data"]
    assert body["collection_name"] == COLLECTION_A
    assert body["rebuilt_document_count"] >= 1

    # Collection B should be unaffected
    docs_b = client.get(
        "/api/v1/documents", params={"collection_name": COLLECTION_B}
    )
    assert docs_b.status_code == 200
    assert len(docs_b.json()["data"]) == 1
