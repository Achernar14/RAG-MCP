import json
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
            "max_file_size_bytes": 1024 * 1024,
            "allow_hidden_files": False,
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


def test_rest_collection_and_document_summary_flow():
    app = create_app()
    client = TestClient(app)

    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"
    ingest = client.post("/api/v1/ingest", json={"path": str(sample_path)})
    assert ingest.status_code == 200
    document_id = ingest.json()["data"]["document_id"]

    collections = client.get("/api/v1/collections")
    assert collections.status_code == 200
    collections_body = collections.json()
    assert collections_body["code"] == 0
    assert collections_body["data"][0]["name"] == "TestRAGMCP"
    assert collections_body["data"][0]["document_count"] >= 1

    documents = client.get("/api/v1/documents")
    assert documents.status_code == 200
    documents_body = documents.json()
    assert documents_body["code"] == 0
    assert documents_body["data"][0]["id"] == document_id
    assert documents_body["data"][0]["chunk_count"] >= 1

    stats = client.get("/api/v1/stats")
    assert stats.status_code == 200
    stats_body = stats.json()
    assert stats_body["code"] == 0
    assert stats_body["data"]["collection_name"] == "TestRAGMCP"
    assert stats_body["data"]["document_count"] >= 1
    assert stats_body["data"]["chunk_count"] >= 1

    summary = client.get(f"/api/v1/documents/{document_id}")
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["code"] == 0
    assert summary_body["data"]["document_id"] == document_id
    assert summary_body["data"]["chunk_count"] >= 1
    assert summary_body["data"]["summary"]

    detail = client.get(f"/api/v1/documents/{document_id}/detail")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["code"] == 0
    assert detail_body["data"]["document_id"] == document_id
    assert detail_body["data"]["chunk_count"] >= 1
    assert detail_body["data"]["content_length"] > 0
    assert detail_body["data"]["chunks"]
    assert detail_body["data"]["chunks"][0]["chunk_id"].startswith(f"{document_id}:")


def test_mcp_collection_and_document_summary_flow():
    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"
    ingest = handle_message(
        {"tool": "knowledge_ingest", "arguments": {"path": str(sample_path)}}
    )
    assert ingest["ok"] is True
    document_id = ingest["data"]["document_id"]

    collections = handle_message({"tool": "list_collections", "arguments": {}})
    assert collections["ok"] is True
    assert collections["data"]
    assert collections["data"][0]["name"] == "TestRAGMCP"

    documents = handle_message({"tool": "list_documents", "arguments": {}})
    assert documents["ok"] is True
    assert documents["data"][0]["id"] == document_id
    assert documents["data"][0]["chunk_count"] >= 1

    status = handle_message({"tool": "knowledge_status", "arguments": {}})
    assert status["ok"] is True
    assert status["data"]["collection_name"] == "TestRAGMCP"
    assert status["data"]["document_count"] >= 1
    assert status["data"]["chunk_count"] >= 1

    summary = handle_message(
        {"tool": "get_document_summary", "arguments": {"document_id": document_id}}
    )
    assert summary["ok"] is True
    assert summary["data"]["document_id"] == document_id
    assert summary["data"]["summary"]

    detail = handle_message(
        {"tool": "get_document_detail", "arguments": {"document_id": document_id}}
    )
    assert detail["ok"] is True
    assert detail["data"]["document_id"] == document_id
    assert detail["data"]["chunk_count"] >= 1
    assert detail["data"]["chunks"]
    assert detail["data"]["chunks"][0]["chunk_id"].startswith(f"{document_id}:")


def test_delete_document_rest_flow_removes_indexes():
    app = create_app()
    client = TestClient(app)

    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"
    ingest = client.post("/api/v1/ingest", json={"path": str(sample_path)})
    document_id = ingest.json()["data"]["document_id"]

    delete_response = client.delete(f"/api/v1/documents/{document_id}")
    assert delete_response.status_code == 200
    delete_body = delete_response.json()
    assert delete_body["code"] == 0
    assert delete_body["data"]["document_id"] == document_id
    assert delete_body["data"]["deleted_chunk_count"] >= 1

    summary = client.get(f"/api/v1/documents/{document_id}")
    assert summary.status_code == 404

    query = client.post("/api/v1/query", json={"query": "modular knowledge retrieval", "top_k": 5})
    query_body = query.json()
    assert query_body["code"] == 0
    assert all(item["chunk_id"].split(":")[0] != document_id for item in query_body["data"]["results"])


def test_delete_document_mcp_flow_removes_indexes():
    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"
    ingest = handle_message(
        {"tool": "knowledge_ingest", "arguments": {"path": str(sample_path)}}
    )
    document_id = ingest["data"]["document_id"]

    deletion = handle_message(
        {"tool": "delete_document", "arguments": {"document_id": document_id}}
    )
    assert deletion["ok"] is True
    assert deletion["data"]["document_id"] == document_id

    summary = handle_message(
        {"tool": "get_document_summary", "arguments": {"document_id": document_id}}
    )
    assert summary["ok"] is False
    assert "Document not found" in summary["error"]

    deletion_missing = handle_message(
        {"tool": "delete_document", "arguments": {"document_id": document_id}}
    )
    assert deletion_missing["ok"] is False
    assert "Document not found" in deletion_missing["error"]


def test_rebuild_collection_replaces_stale_indexes_rest_and_mcp(tmp_path):
    app = create_app()
    client = TestClient(app)

    target_path = tmp_path / "rebuild_target.md"
    original_text = ("fresh section " * 70) + ("obsoletekeyword " * 70)
    target_path.write_text(original_text, encoding="utf-8")

    ingest = client.post("/api/v1/ingest", json={"path": str(target_path)})
    assert ingest.status_code == 200
    document_id = ingest.json()["data"]["document_id"]

    original_summary = client.get(f"/api/v1/documents/{document_id}")
    assert original_summary.status_code == 200
    assert original_summary.json()["data"]["chunk_count"] >= 2

    stale_query = client.post(
        "/api/v1/query",
        json={"query": "obsoletekeyword", "top_k": 5},
    )
    assert stale_query.status_code == 200
    assert stale_query.json()["data"]["results"]

    target_path.write_text("fresh section only after rebuild", encoding="utf-8")

    rebuild = client.post("/api/v1/collections/rebuild")
    assert rebuild.status_code == 200
    rebuild_body = rebuild.json()
    assert rebuild_body["code"] == 0
    assert rebuild_body["data"]["requested_document_count"] == 1
    assert rebuild_body["data"]["rebuilt_document_count"] == 1
    assert rebuild_body["data"]["failed_document_count"] == 0

    status = client.get("/api/v1/stats")
    assert status.status_code == 200
    assert status.json()["data"]["chunk_count"] == 1

    updated_summary = client.get(f"/api/v1/documents/{document_id}")
    assert updated_summary.status_code == 200
    assert updated_summary.json()["data"]["chunk_count"] == 1

    rebuilt_query = client.post(
        "/api/v1/query",
        json={"query": "obsoletekeyword", "top_k": 5},
    )
    assert rebuilt_query.status_code == 200
    rebuilt_results = rebuilt_query.json()["data"]["results"]
    assert rebuilt_results
    assert all("obsoletekeyword" not in item["text"] for item in rebuilt_results)

    settings_path = Path(__import__("os").getenv("RAG_MCP_SETTINGS_PATH"))
    settings = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
    metadata_base = Path(settings["vector_store"]["persist_path"]).parent / settings["vector_store"]["collection_name"]
    bm25_index = json.loads(metadata_base.joinpath("bm25_index.json").read_text(encoding="utf-8"))
    assert all("obsoletekeyword" not in payload["text"] for payload in bm25_index.values())

    mcp_rebuild = handle_message({"tool": "rebuild_collection", "arguments": {}})
    assert mcp_rebuild["ok"] is True
    assert mcp_rebuild["data"]["rebuilt_document_count"] == 1
    assert mcp_rebuild["data"]["failed_document_count"] == 0


def test_rebuild_collection_rejects_unknown_collection():
    app = create_app()
    client = TestClient(app)

    rest_response = client.post("/api/v1/collections/rebuild", params={"collection_name": "unknown"})
    assert rest_response.status_code == 404
    assert "Collection not found" in rest_response.json()["detail"]

    mcp_response = handle_message(
        {"tool": "rebuild_collection", "arguments": {"collection_name": "unknown"}}
    )
    assert mcp_response["ok"] is False
    assert "Collection not found" in mcp_response["error"]


def test_document_detail_returns_not_found_after_delete():
    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"
    ingest = handle_message(
        {"tool": "knowledge_ingest", "arguments": {"path": str(sample_path)}}
    )
    document_id = ingest["data"]["document_id"]

    deletion = handle_message(
        {"tool": "delete_document", "arguments": {"document_id": document_id}}
    )
    assert deletion["ok"] is True

    detail = handle_message(
        {"tool": "get_document_detail", "arguments": {"document_id": document_id}}
    )
    assert detail["ok"] is False
    assert "Document not found" in detail["error"]


def test_ingest_same_content_is_skipped(tmp_path):
    app = create_app()
    client = TestClient(app)

    target_path = tmp_path / "idempotent.md"
    target_path.write_text("same content " * 40, encoding="utf-8")

    first = client.post("/api/v1/ingest", json={"path": str(target_path)})
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["data"]["ingestion_action"] == "created"
    assert first_body["data"]["replaced_existing"] is False

    second = client.post("/api/v1/ingest", json={"path": str(target_path)})
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["data"]["document_id"] == first_body["data"]["document_id"]
    assert second_body["data"]["ingestion_action"] == "skipped"
    assert second_body["data"]["replaced_existing"] is False
    assert second_body["data"]["chunk_count"] == first_body["data"]["chunk_count"]

    documents = client.get("/api/v1/documents")
    assert documents.status_code == 200
    assert len(documents.json()["data"]) == 1

    trace_detail = client.get(f"/api/v1/traces/{second_body['trace_id']}")
    assert trace_detail.status_code == 200
    stages = trace_detail.json()["data"]["stages"]
    assert any(stage["name"] == "precheck" for stage in stages)
    assert any(stage["name"] == "idempotency_check" for stage in stages)
    assert all(stage["name"] != "load" for stage in stages)
    assert all(stage["name"] != "embed" for stage in stages)


def test_ingest_force_rebuild_bypasses_skip_and_replaces_existing(tmp_path):
    app = create_app()
    client = TestClient(app)

    target_path = tmp_path / "force_rebuild.md"
    target_path.write_text("force rebuild content " * 50, encoding="utf-8")

    first = client.post("/api/v1/ingest", json={"path": str(target_path)})
    assert first.status_code == 200
    document_id = first.json()["data"]["document_id"]

    second = client.post(
        "/api/v1/ingest",
        json={"path": str(target_path), "force_rebuild": True},
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["data"]["document_id"] == document_id
    assert second_body["data"]["ingestion_action"] == "replaced"
    assert second_body["data"]["replaced_existing"] is True

    trace_detail = client.get(f"/api/v1/traces/{second_body['trace_id']}")
    assert trace_detail.status_code == 200
    stages = trace_detail.json()["data"]["stages"]
    assert any(stage["name"] == "load" for stage in stages)
    assert any(stage["name"] == "cleanup" for stage in stages)


def test_ingest_rejects_unsupported_file_type(tmp_path):
    app = create_app()
    client = TestClient(app)

    target_path = tmp_path / "unsupported.csv"
    target_path.write_text("a,b,c", encoding="utf-8")

    response = client.post("/api/v1/ingest", json={"path": str(target_path)})
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_ingest_rejects_hidden_file_when_disabled(tmp_path):
    app = create_app()
    client = TestClient(app)

    target_path = tmp_path / ".hidden.md"
    target_path.write_text("hidden content", encoding="utf-8")

    response = client.post("/api/v1/ingest", json={"path": str(target_path)})
    assert response.status_code == 400
    assert "Hidden files are not allowed" in response.json()["detail"]


def test_ingest_rejects_empty_file(tmp_path):
    app = create_app()
    client = TestClient(app)

    target_path = tmp_path / "empty.md"
    target_path.write_text("", encoding="utf-8")

    response = client.post("/api/v1/ingest", json={"path": str(target_path)})
    assert response.status_code == 400
    assert "File is empty" in response.json()["detail"]


def test_ingest_changed_content_replaces_existing_indexes(tmp_path):
    app = create_app()
    client = TestClient(app)

    target_path = tmp_path / "replaceable.md"
    target_path.write_text(("version one " * 60) + ("obsoletephrase " * 60), encoding="utf-8")

    first = client.post("/api/v1/ingest", json={"path": str(target_path)})
    assert first.status_code == 200
    document_id = first.json()["data"]["document_id"]
    assert first.json()["data"]["ingestion_action"] == "created"

    query_before = client.post("/api/v1/query", json={"query": "obsoletephrase", "top_k": 5})
    assert query_before.status_code == 200
    assert query_before.json()["data"]["results"]

    target_path.write_text("version two only", encoding="utf-8")

    second = client.post("/api/v1/ingest", json={"path": str(target_path)})
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["data"]["document_id"] == document_id
    assert second_body["data"]["ingestion_action"] == "replaced"
    assert second_body["data"]["replaced_existing"] is True

    documents = client.get("/api/v1/documents")
    assert documents.status_code == 200
    assert len(documents.json()["data"]) == 1

    summary = client.get(f"/api/v1/documents/{document_id}")
    assert summary.status_code == 200
    assert summary.json()["data"]["chunk_count"] == 1
    metadata = summary.json()["data"]["summary"]
    assert metadata is not None

    query_after = client.post("/api/v1/query", json={"query": "obsoletephrase", "top_k": 5})
    assert query_after.status_code == 200
    assert all("obsoletephrase" not in item["text"] for item in query_after.json()["data"]["results"])


def test_document_detail_exposes_enriched_file_metadata(tmp_path):
    app = create_app()
    client = TestClient(app)

    target_path = tmp_path / "metadata.md"
    target_path.write_text("line one\nline two\nline three", encoding="utf-8")

    ingest = client.post("/api/v1/ingest", json={"path": str(target_path)})
    assert ingest.status_code == 200
    document_id = ingest.json()["data"]["document_id"]

    detail = client.get(f"/api/v1/documents/{document_id}/detail")
    assert detail.status_code == 200
    metadata = detail.json()["data"]["metadata"]
    assert metadata["source_name"] == "metadata.md"
    assert metadata["source_extension"] == ".md"
    assert metadata["loader_name"] == "TextDocumentLoader"
    assert metadata["line_count"] == 3
    assert metadata["word_count"] == 6
    assert metadata["non_empty_char_count"] > 0
    assert metadata["contains_cjk"] is False
    assert metadata["source_size_bytes"] > 0
    assert metadata["source_bytes_fingerprint"]
    assert metadata["content_fingerprint"]


def test_document_detail_detects_cjk_metadata(tmp_path):
    app = create_app()
    client = TestClient(app)

    target_path = tmp_path / "cjk.md"
    target_path.write_text("这是中文内容。\nSecond line.", encoding="utf-8")

    ingest = client.post("/api/v1/ingest", json={"path": str(target_path)})
    assert ingest.status_code == 200
    document_id = ingest.json()["data"]["document_id"]

    detail = client.get(f"/api/v1/documents/{document_id}/detail")
    assert detail.status_code == 200
    metadata = detail.json()["data"]["metadata"]
    assert metadata["contains_cjk"] is True
