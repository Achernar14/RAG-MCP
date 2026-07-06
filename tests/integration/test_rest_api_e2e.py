"""Integration test: REST API end-to-end flow.

Exercises the full lifecycle — health → ingest → query → generate answer →
document management → stats → delete — against a real Chroma vector store
with hash embeddings, verifying correct status codes, response shapes, and
data consistency.
"""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from rag_mcp.core.container import reset_container
from rag_mcp.main import create_app


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    """Create an isolated test environment."""
    reset_container()
    runtime_root = tmp_path / "runtime"
    settings_path = tmp_path / "settings.yaml"
    settings_payload = {
        "app": {"name": "rag-mcp-e2e", "environment": "test"},
        "embedding": {"provider": "hash", "dimensions": 64},
        "vector_store": {
            "provider": "chroma",
            "collection_name": "e2e_test",
            "persist_path": str(runtime_root / "vector_store" / "chroma_live"),
        },
        "ingestion": {
            "chunk_size": 500,
            "chunk_overlap": 50,
            "normalize_whitespace": True,
            "preserve_paragraph_breaks": True,
            "boundary_scan_chars": 80,
            "min_chunk_length": 40,
            "max_file_size_bytes": 20971520,
            "allow_hidden_files": False,
            "supported_extensions": [".txt", ".md", ".pdf", ".html"],
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
        "rerank": {"provider": "lexical", "enabled": True},
        "observability": {
            "trace_enabled": True,
            "trace_path": str(runtime_root / "traces" / "traces.jsonl"),
        },
        "evaluation": {
            "enabled": True,
            "report_path": str(runtime_root / "evaluations" / "reports.jsonl"),
            "default_test_set_path": "data/evaluations/golden_test_set.json",
            "metrics": ["hit_rate", "mrr"],
            "top_k": 5,
            "persist_reports": True,
        },
        "prompts": {
            "answer_system_prompt_path": "config/prompts/answer_system.txt",
            "answer_user_prompt_path": "config/prompts/answer_user.txt",
        },
        "mcp": {"server_name": "rag-mcp-e2e", "server_version": "0.1.0"},
        "api": {"host": "127.0.0.1", "port": 8000},
    }
    settings_path.write_text(yaml.safe_dump(settings_payload), encoding="utf-8")
    monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))
    runtime_root.mkdir(parents=True, exist_ok=True)
    yield runtime_root
    reset_container()


# ── Full lifecycle test ─────────────────────────────────────────────


def test_full_rest_api_lifecycle():
    """Health → Ingest → Query → Generate Answer → Documents → Stats → Delete."""
    app = create_app()
    client = TestClient(app)
    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"

    # 1. Health check
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["data"]["status"] == "healthy"

    # 2. Ingest a document
    ingest = client.post("/api/v1/ingest", json={"path": str(sample_path)})
    assert ingest.status_code == 200
    ingest_data = ingest.json()["data"]
    assert ingest_data["chunk_count"] >= 1
    assert ingest_data["ingestion_action"] == "created"
    document_id = ingest_data["document_id"]

    # 3. Query the knowledge base
    query = client.post("/api/v1/query", json={"query": "What does the MVP support?", "top_k": 3})
    assert query.status_code == 200
    query_data = query.json()["data"]
    assert len(query_data["results"]) >= 1
    assert query_data["rerank_applied"] is True
    assert len(query_data["sources"]) >= 1
    trace_id = query_data["trace_id"]

    # 4. Generate an answer
    answer = client.post(
        "/api/v1/answers/generate",
        json={"query": "What does the MVP support?", "top_k": 3},
    )
    assert answer.status_code == 200
    answer_data = answer.json()["data"]
    assert len(answer_data["answer"]) > 0
    assert answer_data["generated_by_llm"] is True
    assert len(answer_data["sources"]) >= 1

    # 5. Stats
    stats = client.get("/api/v1/stats")
    assert stats.status_code == 200
    stats_data = stats.json()["data"]
    assert stats_data["document_count"] >= 1
    assert stats_data["chunk_count"] >= 1
    assert stats_data["collection_name"] == "e2e_test"

    # 6. List collections
    collections = client.get("/api/v1/collections")
    assert collections.status_code == 200
    coll_data = collections.json()["data"]
    assert len(coll_data) >= 1
    assert coll_data[0]["name"] == "e2e_test"

    # 7. List documents
    docs = client.get("/api/v1/documents")
    assert docs.status_code == 200
    docs_data = docs.json()["data"]
    assert len(docs_data) == 1
    assert docs_data[0]["id"] == document_id

    # 8. Get document summary
    summary = client.get(f"/api/v1/documents/{document_id}")
    assert summary.status_code == 200
    summary_data = summary.json()["data"]
    assert summary_data["document_id"] == document_id
    assert len(summary_data["summary"]) > 0

    # 9. Get document detail
    detail = client.get(f"/api/v1/documents/{document_id}/detail")
    assert detail.status_code == 200
    detail_data = detail.json()["data"]
    assert detail_data["document_id"] == document_id
    assert len(detail_data["chunks"]) >= 1
    assert detail_data["chunks"][0]["chunk_id"].startswith(f"{document_id}:")

    # 10. Get trace
    trace = client.get(f"/api/v1/traces/{trace_id}")
    assert trace.status_code == 200
    trace_data = trace.json()["data"]
    assert trace_data["trace_id"] == trace_id
    assert trace_data["trace_type"] == "query"
    assert len(trace_data["stages"]) >= 1

    # 11. Delete document
    delete = client.delete(f"/api/v1/documents/{document_id}")
    assert delete.status_code == 200
    delete_data = delete.json()["data"]
    assert delete_data["document_id"] == document_id
    assert delete_data["deleted_chunk_count"] >= 1

    # 12. Verify deletion
    docs_after = client.get("/api/v1/documents")
    assert docs_after.status_code == 200
    assert len(docs_after.json()["data"]) == 0

    stats_after = client.get("/api/v1/stats")
    assert stats_after.status_code == 200
    assert stats_after.json()["data"]["document_count"] == 0

    # 13. Deleted document returns 404
    deleted_summary = client.get(f"/api/v1/documents/{document_id}")
    assert deleted_summary.status_code == 404


# ── Error handling tests ─────────────────────────────────────────────


def test_ingest_nonexistent_file():
    """Ingesting a non-existent file should return 400."""
    app = create_app()
    client = TestClient(app)

    response = client.post("/api/v1/ingest", json={"path": "/nonexistent/file.md"})
    assert response.status_code == 400


def test_query_empty_string():
    """Querying with an empty string should fail validation."""
    app = create_app()
    client = TestClient(app)

    response = client.post("/api/v1/query", json={"query": "", "top_k": 3})
    assert response.status_code == 422


def test_document_detail_not_found():
    """Requesting a non-existent document should return 404."""
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/documents/nonexistent-id/detail")
    assert response.status_code == 404


def test_trace_not_found():
    """Requesting a non-existent trace should return 404."""
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/traces/nonexistent-trace")
    assert response.status_code == 404
