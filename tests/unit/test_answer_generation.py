from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from rag_mcp.core.container import reset_container
from rag_mcp.main import create_app
from rag_mcp.mcp.protocol import handle_message
from rag_mcp.observability.dashboard.services import DashboardService


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    reset_container()
    runtime_root = tmp_path / "runtime"
    settings_path = tmp_path / "settings.yaml"
    settings_payload = {
        "app": {"name": "rag-mcp", "environment": "test"},
        "embedding": {"provider": "hash", "dimensions": 64},
        "embedding_provider": {
            "api_base": None,
            "api_key_env": "OPENAI_API_KEY",
            "model": None,
            "timeout_seconds": 30.0,
        },
        "llm": {
            "provider": "stub",
            "enabled": False,
            "api_base": None,
            "api_key_env": "OPENAI_API_KEY",
            "model": None,
            "temperature": 0.1,
            "max_tokens": 1024,
            "timeout_seconds": 60.0,
        },
        "vision_llm": {
            "provider": "disabled",
            "enabled": False,
            "api_base": None,
            "api_key_env": "OPENAI_API_KEY",
            "model": None,
            "timeout_seconds": 60.0,
        },
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
        "rerank": {
            "provider": "lexical",
            "enabled": True,
            "model": None,
            "api_base": None,
            "api_key_env": "RERANK_API_KEY",
            "score_threshold": None,
            "timeout_seconds": 30.0,
        },
        "observability": {
            "trace_enabled": True,
            "trace_path": str(runtime_root / "traces" / "traces.jsonl"),
        },
        "evaluation": {
            "enabled": True,
            "report_path": str(runtime_root / "evaluations" / "reports.jsonl"),
            "default_test_set_path": str(runtime_root / "evaluations" / "golden_test_set.json"),
            "metrics": ["hit_rate", "mrr"],
            "top_k": 5,
            "persist_reports": True,
        },
        "prompts": {
            "answer_system_prompt_path": "config/prompts/answer_system.txt",
            "answer_user_prompt_path": "config/prompts/answer_user.txt",
        },
        "mcp": {"server_name": "rag-mcp", "server_version": "0.1.0"},
        "api": {"host": "127.0.0.1", "port": 8000},
    }
    settings_path.write_text(yaml.safe_dump(settings_payload), encoding="utf-8")
    monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))
    runtime_root.mkdir(parents=True, exist_ok=True)
    yield
    reset_container()


def _ingest_sample(client: TestClient) -> None:
    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"
    response = client.post("/api/v1/ingest", json={"path": str(sample_path)})
    assert response.status_code == 200


def test_rest_generate_answer_flow():
    app = create_app()
    client = TestClient(app)
    _ingest_sample(client)

    response = client.post(
        "/api/v1/answers/generate",
        json={"query": "What does the MVP support?", "top_k": 3},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["answer"]
    assert body["data"]["results"]
    assert body["data"]["sources"]
    assert body["data"]["generated_by_llm"] is True
    assert "Grounded answer" in body["data"]["answer"]


def test_mcp_generate_answer_flow():
    app = create_app()
    client = TestClient(app)
    _ingest_sample(client)

    response = handle_message(
        {"tool": "generate_answer", "arguments": {"query": "What does the MVP support?", "top_k": 3}}
    )
    assert response["ok"] is True
    assert response["data"]["answer"]
    assert response["data"]["sources"]


def test_dashboard_service_generate_answer_flow():
    app = create_app()
    client = TestClient(app)
    _ingest_sample(client)

    service = DashboardService()
    response = service.generate_answer("What does the MVP support?", top_k=3)
    assert response["answer"]
    assert response["results"]
    assert response["sources"]
