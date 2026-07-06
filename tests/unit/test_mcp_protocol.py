from pathlib import Path

import pytest
import yaml

from rag_mcp.core.container import reset_container
from rag_mcp.mcp.protocol import handle_message


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
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
    yield
    reset_container()


def test_mcp_ingest_query_and_status():
    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"

    ingest = handle_message(
        {"tool": "knowledge_ingest", "arguments": {"path": str(sample_path)}}
    )
    assert ingest["ok"] is True
    assert ingest["data"]["chunk_count"] >= 1

    query = handle_message(
        {"tool": "knowledge_query", "arguments": {"query": "dense retrieval", "top_k": 2}}
    )
    assert query["ok"] is True
    assert query["data"]["results"]

    status = handle_message({"tool": "knowledge_status", "arguments": {}})
    assert status["ok"] is True
    assert status["data"]["document_count"] >= 1
    assert status["data"]["chunk_count"] >= 1
    assert status["data"]["collection_name"] == "TestRAGMCP"

    documents = handle_message({"tool": "list_documents", "arguments": {}})
    assert documents["ok"] is True
    assert len(documents["data"]) == 1
    assert documents["data"][0]["filename"] == sample_path.name


def test_mcp_jsonrpc_initialize_tools_list_and_call():
    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"

    init_response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "0.1.0"}},
        }
    )
    assert init_response["jsonrpc"] == "2.0"
    assert init_response["id"] == 1
    assert init_response["result"]["protocolVersion"] == "2025-06-18"
    assert init_response["result"]["capabilities"]["tools"] == {}

    tools_response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }
    )
    assert tools_response["jsonrpc"] == "2.0"
    tool_names = {tool["name"] for tool in tools_response["result"]["tools"]}
    assert "knowledge_ingest" in tool_names
    assert "knowledge_query" in tool_names
    assert "generate_answer" in tool_names

    ingest_response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "knowledge_ingest", "arguments": {"path": str(sample_path)}},
        }
    )
    assert ingest_response["jsonrpc"] == "2.0"
    assert ingest_response["result"]["isError"] is False
    ingest_structured = ingest_response["result"]["structuredContent"]
    assert ingest_structured["chunk_count"] >= 1

    query_response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "knowledge_query", "arguments": {"query": "dense retrieval", "top_k": 2}},
        }
    )
    assert query_response["jsonrpc"] == "2.0"
    assert query_response["result"]["isError"] is False
    assert query_response["result"]["structuredContent"]["results"]


def test_mcp_jsonrpc_tools_call_returns_is_error_for_not_found():
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "get_document_detail", "arguments": {"document_id": "missing-doc"}},
        }
    )
    assert response["jsonrpc"] == "2.0"
    assert response["result"]["isError"] is True
    assert "Document not found" in response["result"]["content"][0]["text"]


def test_mcp_jsonrpc_initialized_notification_returns_none():
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
    )
    assert response is None
