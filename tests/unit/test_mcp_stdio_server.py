import os
import sys
from pathlib import Path

import anyio
import pytest
import yaml
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

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
        "mcp": {"server_name": "rag-mcp-stdio", "server_version": "0.2.0"},
        "api": {"host": "127.0.0.1", "port": 8000},
    }
    settings_path.write_text(yaml.safe_dump(settings_payload), encoding="utf-8")
    monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))
    runtime_root.mkdir(parents=True, exist_ok=True)
    yield
    reset_container()


def test_stdio_server_initialize_and_call_tool():
    repo_root = Path(__file__).resolve().parents[2]
    sample_path = repo_root / "data" / "documents" / "sample.md"

    # Ingest via REST path first — MCP no longer exposes management tools.
    from rag_mcp.core.container import reset_container as _rc
    _rc()
    import yaml as _yaml, os as _os
    _settings_path = _os.environ["RAG_MCP_SETTINGS_PATH"]
    from rag_mcp.core.settings import load_settings
    from rag_mcp.core.container import ApplicationContainer
    _settings = load_settings(_settings_path)
    _container = ApplicationContainer(_settings)
    from rag_mcp.application.dto.models import IngestRequest
    _container.ingest_use_case.execute(IngestRequest(path=str(sample_path)))
    _container.close()

    async def scenario() -> None:
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "rag_mcp.mcp.server"],
            env={
                "PYTHONPATH": str((repo_root / "backend" / "src").resolve()),
                "RAG_MCP_SETTINGS_PATH": os.environ["RAG_MCP_SETTINGS_PATH"],
            },
            cwd=repo_root,
        )

        async with stdio_client(server_params) as streams:
            async with ClientSession(*streams) as session:
                initialize = await session.initialize()
                assert initialize.serverInfo.name == "rag-mcp-stdio"
                assert initialize.serverInfo.version == "0.2.0"

                tools = await session.list_tools()
                tool_names = {tool.name for tool in tools.tools}
                # MCP only exposes read-only knowledge tools:
                assert tool_names == {"knowledge_search", "list_documents", "list_collections"}

                # knowledge_search works
                result = await session.call_tool(
                    "knowledge_search",
                    {"query": "dense retrieval", "top_k": 2},
                )
                assert result.isError is False
                assert result.structuredContent["results"]

                # Management tools are NOT exposed:
                ingest = await session.call_tool(
                    "knowledge_ingest",
                    {"path": str(sample_path)},
                )
                assert ingest.isError is True

    anyio.run(scenario, backend="asyncio")
