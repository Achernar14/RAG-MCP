import asyncio
from pathlib import Path

import pytest
import yaml

from rag_mcp.core.container import reset_container
from rag_mcp.mcp.sdk_server import create_fastmcp_server


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
        "mcp": {"server_name": "rag-mcp-sdk", "server_version": "0.1.0"},
        "api": {"host": "127.0.0.1", "port": 8000},
    }
    settings_path.write_text(yaml.safe_dump(settings_payload), encoding="utf-8")
    monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))
    runtime_root.mkdir(parents=True, exist_ok=True)
    yield
    reset_container()


def test_sdk_server_lists_tools_and_calls_core_flows():
    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"
    server = create_fastmcp_server()

    tools = asyncio.run(server.list_tools())
    tool_names = {tool.name for tool in tools}

    assert "knowledge_ingest" in tool_names
    assert "knowledge_query" in tool_names
    assert "generate_answer" in tool_names
    assert "list_documents" in tool_names

    _, ingest_structured = asyncio.run(
        server.call_tool("knowledge_ingest", {"path": str(sample_path)})
    )
    assert ingest_structured["chunk_count"] >= 1

    _, query_structured = asyncio.run(
        server.call_tool("knowledge_query", {"query": "dense retrieval", "top_k": 2})
    )
    assert query_structured["results"]
    assert query_structured["trace_id"]

    _, answer_structured = asyncio.run(
        server.call_tool("generate_answer", {"query": "What does the MVP support?", "top_k": 2})
    )
    assert answer_structured["answer"]
    assert answer_structured["sources"]

    _, documents_structured = asyncio.run(server.call_tool("list_documents", {}))
    assert documents_structured["result"]
    assert documents_structured["result"][0]["filename"] == sample_path.name


def test_sdk_server_uses_configured_server_name():
    server = create_fastmcp_server()

    assert server.name == "rag-mcp-sdk"


def test_sdk_server_is_cached_within_runtime():
    first = create_fastmcp_server()
    second = create_fastmcp_server()

    assert first is second
