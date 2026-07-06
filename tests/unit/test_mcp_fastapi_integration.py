"""Tests for FastAPI + MCP Streamable HTTP integration."""

import pytest
import yaml

from rag_mcp.core.container import reset_container


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
        "mcp": {
            "server_name": "rag-mcp-integration",
            "server_version": "0.1.0",
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
    reset_container()


def test_app_mounts_mcp_when_streamable_http():
    """When transport is streamable-http, the FastAPI app should mount MCP at /mcp."""
    from unittest.mock import patch
    from fastapi import FastAPI
    from rag_mcp.main import create_app

    # Need to reset fastmcp server too
    from rag_mcp.mcp.sdk_server import reset_fastmcp_server
    reset_fastmcp_server()

    app = create_app()
    # The app should have routes for both REST API and MCP
    routes = [route.path for route in app.routes]
    assert "/api/v1/health" in routes
    # MCP is mounted as a sub-app at /mcp
    mount_names = [route.path for route in app.routes if hasattr(route, "path")]
    assert "/mcp" in mount_names

    reset_fastmcp_server()


def test_app_no_mcp_mount_when_stdio(tmp_path, monkeypatch):
    """When transport is stdio, the FastAPI app should NOT mount MCP."""
    from rag_mcp.mcp.sdk_server import reset_fastmcp_server

    reset_container()
    reset_fastmcp_server()

    settings_path = tmp_path / "settings_stdio.yaml"
    settings_payload = {
        "app": {"name": "rag-mcp", "environment": "test"},
        "embedding": {"provider": "hash", "dimensions": 64},
        "vector_store": {
            "provider": "chroma",
            "collection_name": "TestRAGMCP",
            "persist_path": str(tmp_path / "runtime" / "vector_store" / "chroma_live"),
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
            "trace_path": str(tmp_path / "runtime" / "traces" / "traces.jsonl"),
        },
        "mcp": {
            "server_name": "rag-mcp-stdio-test",
            "server_version": "0.1.0",
            "transport": "stdio",
            "host": "127.0.0.1",
            "port": 9000,
            "mount_path": "/mcp",
        },
        "api": {"host": "127.0.0.1", "port": 8000},
    }
    settings_path.write_text(yaml.safe_dump(settings_payload), encoding="utf-8")
    monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))

    from rag_mcp.main import create_app
    app = create_app()
    routes = [route.path for route in app.routes]
    assert "/api/v1/health" in routes
    # /mcp should NOT be mounted
    mount_paths = [route.path for route in app.routes if hasattr(route, "path")]
    assert "/mcp" not in mount_paths

    reset_fastmcp_server()
    reset_container()
