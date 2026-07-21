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

    # Ingest via REST path (container directly) — MCP no longer exposes
    # management tools.
    from rag_mcp.core.container import get_container
    from rag_mcp.application.dto.models import IngestRequest
    container = get_container()
    container.ingest_use_case.execute(
        IngestRequest(path=str(sample_path))
    )

    # MCP query tool is now named knowledge_search (was knowledge_query)
    query = handle_message(
        {"tool": "knowledge_search", "arguments": {"query": "dense retrieval", "top_k": 2}}
    )
    assert query["ok"] is True
    assert query["data"]["results"]

    # Management tools (knowledge_ingest, knowledge_status) are not MCP tools:
    ingest_attempt = handle_message(
        {"tool": "knowledge_ingest", "arguments": {"path": str(sample_path)}}
    )
    assert ingest_attempt["ok"] is False

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
    # MCP now only exposes read-only knowledge tools:
    assert "knowledge_search" in tool_names
    assert "list_documents" in tool_names
    assert "list_collections" in tool_names
    # Management tools and generate_answer are NOT MCP tools:
    assert "knowledge_ingest" not in tool_names
    assert "generate_answer" not in tool_names

    # Ingest via REST path first so there is data to search.
    from rag_mcp.core.container import get_container
    from rag_mcp.application.dto.models import IngestRequest
    container = get_container()
    container.ingest_use_case.execute(
        IngestRequest(path=str(sample_path))
    )

    # tools/call: knowledge_search
    query_response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "knowledge_search", "arguments": {"query": "dense retrieval", "top_k": 2}},
        }
    )
    assert query_response["jsonrpc"] == "2.0"
    assert query_response["result"]["isError"] is False
    assert query_response["result"]["structuredContent"]["results"]


def test_mcp_jsonrpc_tools_call_returns_is_error_for_not_found():
    # Calling an unregistered tool returns isError.
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "non_existent_tool", "arguments": {}},
        }
    )
    assert response["jsonrpc"] == "2.0"
    assert response["result"]["isError"] is True
    assert "Unknown tool" in response["result"]["content"][0]["text"]


def test_mcp_jsonrpc_initialized_notification_returns_none():
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
    )
    assert response is None
