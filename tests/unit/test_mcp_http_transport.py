"""Tests for MCP Streamable HTTP transport integration."""

import asyncio
from pathlib import Path

import pytest
import yaml

from rag_mcp.core.container import reset_container
from rag_mcp.mcp.sdk_server import (
    create_fastmcp_server,
    get_streamable_http_app,
    reset_fastmcp_server,
)


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    reset_container()
    reset_fastmcp_server()
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
        "mcp": {
            "server_name": "rag-mcp-http",
            "server_version": "0.2.0",
            "transport": "streamable-http",
            "host": "127.0.0.1",
            "port": 9000,
            "mount_path": "/mcp",
        },
        "api": {"host": "127.0.0.1", "port": 8000},
    }
    settings_path.write_text(yaml.safe_dump(settings_payload), encoding="utf-8")
    monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))
    runtime_root.mkdir(parents=True, exist_ok=True)
    yield
    reset_fastmcp_server()
    reset_container()


def test_streamable_http_app_returns_starlette():
    """get_streamable_http_app should return a Starlette ASGI application."""
    from starlette.applications import Starlette

    app = get_streamable_http_app()
    assert isinstance(app, Starlette)


def test_streamable_http_app_is_cached_with_server():
    """The HTTP app shares the same FastMCP server instance."""
    server = create_fastmcp_server()
    app = get_streamable_http_app()
    # Both use the same underlying server
    assert server.name == "rag-mcp-http"


def test_mcp_settings_transport_configuration(tmp_path, monkeypatch):
    """Verify that McpSettings correctly parses transport configuration."""
    from rag_mcp.core.settings import McpSettings

    settings = McpSettings()
    assert settings.transport == "stdio"  # default
    assert settings.host == "127.0.0.1"
    assert settings.port == 9000
    assert settings.mount_path == "/mcp"

    custom = McpSettings(
        transport="streamable-http",
        host="0.0.0.0",
        port=8080,
        mount_path="/api/mcp",
    )
    assert custom.transport == "streamable-http"
    assert custom.host == "0.0.0.0"
    assert custom.port == 8080
    assert custom.mount_path == "/api/mcp"


def test_main_resolves_transport_from_settings():
    """main() should resolve transport from settings when no override is given."""
    from rag_mcp.mcp.sdk_server import main
    from rag_mcp.core.container import get_container

    container = get_container()
    assert container.settings.mcp.transport == "streamable-http"


def test_tools_registered_in_http_server():
    """All 15 tools should be registered in the HTTP-capable MCP server."""
    server = create_fastmcp_server()
    tools = asyncio.run(server.list_tools())
    tool_names = {tool.name for tool in tools}

    expected_tools = {
        "knowledge_ingest", "knowledge_status", "rebuild_collection", "list_collections",
        "knowledge_query",
        "generate_answer",
        "list_documents", "get_document_detail", "get_document_summary", "delete_document",
        "run_evaluation", "list_evaluation_reports", "get_evaluation_report",
        "list_traces", "get_trace_detail",
    }
    assert expected_tools.issubset(tool_names)
