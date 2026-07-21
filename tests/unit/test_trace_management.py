from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from rag_mcp.core.container import reset_container
from rag_mcp.main import create_app
from rag_mcp.mcp.protocol import handle_message


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
            "collection_name": "TestRAGMCP",
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
    yield
    reset_container()


def test_rest_trace_list_and_detail_flow():
    app = create_app()
    client = TestClient(app)
    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"

    ingest = client.post("/api/v1/ingest", json={"path": str(sample_path)})
    assert ingest.status_code == 200
    ingest_trace_id = ingest.json()["trace_id"]

    query = client.post("/api/v1/query", json={"query": "dense retrieval", "top_k": 2})
    assert query.status_code == 200
    query_trace_id = query.json()["trace_id"]

    traces = client.get("/api/v1/traces")
    assert traces.status_code == 200
    traces_body = traces.json()
    assert traces_body["code"] == 0
    assert len(traces_body["data"]) >= 2
    assert {item["trace_id"] for item in traces_body["data"]} >= {ingest_trace_id, query_trace_id}

    query_traces = client.get("/api/v1/traces", params={"trace_type": "query", "limit": 1})
    assert query_traces.status_code == 200
    filtered = query_traces.json()["data"]
    assert len(filtered) == 1
    assert filtered[0]["trace_type"] == "query"

    trace_detail = client.get(f"/api/v1/traces/{query_trace_id}")
    assert trace_detail.status_code == 200
    detail_body = trace_detail.json()
    assert detail_body["code"] == 0
    assert detail_body["data"]["trace_id"] == query_trace_id
    assert detail_body["data"]["trace_type"] == "query"
    assert detail_body["data"]["stages"]
    assert any(stage["name"] == "dense_retrieval" for stage in detail_body["data"]["stages"])


def test_mcp_trace_list_and_detail_not_exposed():
    """Trace browsing is NOT an MCP tool — diagnostics go through REST."""
    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"

    # Ingest and query via REST (container directly):
    from rag_mcp.core.container import get_container
    from rag_mcp.application.dto.models import IngestRequest
    container = get_container()
    container.ingest_use_case.execute(IngestRequest(path=str(sample_path)))

    query_response = container.query_use_case.execute(
        type("QueryRequest", (), {"query": "dense retrieval", "top_k": 2, "collection_name": None})()
    )
    # Actually use the correct DTO:
    from rag_mcp.application.dto.models import QueryRequest
    qr = container.query_use_case.execute(QueryRequest(query="dense retrieval", top_k=2))
    assert qr.trace_id

    # Trace tools are NOT MCP tools:
    traces = handle_message({"tool": "list_traces", "arguments": {"trace_type": "query", "limit": 5}})
    assert traces["ok"] is False

    detail = handle_message(
        {"tool": "get_trace_detail", "arguments": {"trace_id": qr.trace_id}}
    )
    assert detail["ok"] is False
