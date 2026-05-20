from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from rag_mcp.core.container import reset_container
from rag_mcp.main import create_app


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    reset_container()
    runtime_root = tmp_path / "runtime"
    settings_path = tmp_path / "settings.yaml"
    settings_payload = {
        "app": {"name": "rag-mcp", "environment": "test"},
        "embedding": {"provider": "hash", "dimensions": 64},
        "vector_store": {
            "provider": "chroma",
            "persist_path": str(runtime_root / "vector_store" / "chroma"),
            "collection_name": "hybrid_test_collection",
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
    yield
    reset_container()


def test_hybrid_query_exposes_retrieval_method():
    app = create_app()
    client = TestClient(app)

    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "bm25_sample.md"
    ingest_response = client.post("/api/v1/ingest", json={"path": str(sample_path)})
    assert ingest_response.status_code == 200

    query_response = client.post(
        "/api/v1/query",
        json={"query": "BM25 exact term matching", "top_k": 3},
    )
    assert query_response.status_code == 200
    body = query_response.json()
    assert body["code"] == 0
    assert body["data"]["results"]
    assert body["data"]["rerank_applied"] is True
    methods = [item["retrieval_method"] for item in body["data"]["results"]]
    assert any(method and "rerank" in method for method in methods)


def test_sparse_index_file_created():
    app = create_app()
    client = TestClient(app)

    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "bm25_sample.md"
    client.post("/api/v1/ingest", json={"path": str(sample_path)})

    settings_file = Path(__import__("os").getenv("RAG_MCP_SETTINGS_PATH"))
    settings = yaml.safe_load(settings_file.read_text(encoding="utf-8"))
    base = Path(settings["vector_store"]["persist_path"]).parent
    assert base.joinpath("bm25_index.json").exists()


def test_rerank_marks_results():
    app = create_app()
    client = TestClient(app)

    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "bm25_sample.md"
    client.post("/api/v1/ingest", json={"path": str(sample_path)})

    response = client.post(
        "/api/v1/query",
        json={"query": "unique keywords exact term matching", "top_k": 3},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["rerank_applied"] is True
    assert all(
        item["retrieval_method"] and "rerank" in item["retrieval_method"]
        for item in body["data"]["results"]
    )
