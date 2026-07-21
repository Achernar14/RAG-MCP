from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from rag_mcp.factory import reset_container
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
        "retrieval": {"top_k": 5},
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


def test_ingest_and_query_flow():
    app = create_app()
    client = TestClient(app)

    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"

    ingest_response = client.post(
        "/api/v1/ingest",
        json={"path": str(sample_path)},
    )
    assert ingest_response.status_code == 200
    ingest_body = ingest_response.json()
    assert ingest_body["code"] == 0
    assert ingest_body["data"]["chunk_count"] >= 1

    query_response = client.post(
        "/api/v1/query",
        json={"query": "What does the MVP support?", "top_k": 3},
    )
    assert query_response.status_code == 200
    query_body = query_response.json()
    assert query_body["code"] == 0
    assert query_body["data"]["results"]
    assert query_body["data"]["sources"]
    settings_file = Path(__import__("os").getenv("RAG_MCP_SETTINGS_PATH"))
    settings = yaml.safe_load(settings_file.read_text(encoding="utf-8"))
    metadata_base = Path(settings["vector_store"]["persist_path"]).parent / settings["vector_store"]["collection_name"]
    assert metadata_base.joinpath("documents.json").exists()


def test_documents_endpoint():
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/documents")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0


def test_pdf_ingest_and_query_flow():
    app = create_app()
    client = TestClient(app)

    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.pdf"

    ingest_response = client.post(
        "/api/v1/ingest",
        json={"path": str(sample_path)},
    )
    assert ingest_response.status_code == 200
    ingest_body = ingest_response.json()
    assert ingest_body["code"] == 0
    assert ingest_body["data"]["chunk_count"] >= 1
    document_id = ingest_body["data"]["document_id"]

    query_response = client.post(
        "/api/v1/query",
        json={"query": "PDF ingestion chroma persistence", "top_k": 3},
    )
    assert query_response.status_code == 200
    query_body = query_response.json()
    assert query_body["code"] == 0
    assert query_body["data"]["results"]

    detail_response = client.get(f"/api/v1/documents/{document_id}/detail")
    assert detail_response.status_code == 200
    detail_body = detail_response.json()["data"]
    assert detail_body["doc_type"] == "pdf"
    assert detail_body["assets"] == []
    assert detail_body["metadata"]["multimodal_status"] == "skeleton_only"
    assert detail_body["metadata"]["image_asset_count"] == 0


def test_persistence_files_created():
    app = create_app()
    client = TestClient(app)

    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"
    client.post("/api/v1/ingest", json={"path": str(sample_path)})

    from os import getenv
    settings_file = Path(getenv("RAG_MCP_SETTINGS_PATH"))
    settings = yaml.safe_load(settings_file.read_text(encoding="utf-8"))
    base = Path(settings["vector_store"]["persist_path"]).parent
    collection_dir = base / settings["vector_store"]["collection_name"]
    assert collection_dir.joinpath("documents.json").exists()
    assert collection_dir.joinpath("chunks.json").exists()
    assert collection_dir.joinpath("chroma_live").exists()
    assert collection_dir.joinpath("bm25_index.json").exists()
