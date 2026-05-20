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
            "persist_path": str(runtime_root / "vector_store" / "chroma"),
            "collection_name": "evaluation_test_collection",
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

    evaluation_dir = runtime_root / "evaluations"
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    (evaluation_dir / "golden_test_set.json").write_text(
        (
            '{'
            '"dataset_name":"evaluation_suite",'
            '"cases":['
            '{"case_id":"case_1","query":"What does the MVP support?","expected_source_paths":["sample.md"]},'
            '{"case_id":"case_2","query":"BM25 exact term matching","expected_source_paths":["bm25_sample.md"]}'
            "]}"
        ),
        encoding="utf-8",
    )

    runtime_root.mkdir(parents=True, exist_ok=True)
    yield
    reset_container()


def _ingest_samples(client: TestClient) -> None:
    data_root = Path(__file__).resolve().parents[2] / "data" / "documents"
    sample_paths = [data_root / "sample.md", data_root / "bm25_sample.md"]
    for sample_path in sample_paths:
        response = client.post("/api/v1/ingest", json={"path": str(sample_path)})
        assert response.status_code == 200


def test_rest_evaluation_flow():
    app = create_app()
    client = TestClient(app)
    _ingest_samples(client)

    run_response = client.post("/api/v1/evaluations/run", json={})
    assert run_response.status_code == 200
    body = run_response.json()
    assert body["code"] == 0
    assert body["data"]["summary"]["total_cases"] == 2
    assert body["data"]["summary"]["hit_rate"] >= 0.5
    report_id = body["data"]["report_id"]

    list_response = client.get("/api/v1/evaluations")
    assert list_response.status_code == 200
    reports = list_response.json()["data"]
    assert reports
    assert reports[0]["report_id"] == report_id

    detail_response = client.get(f"/api/v1/evaluations/{report_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["report_id"] == report_id
    assert len(detail["cases"]) == 2


def test_mcp_evaluation_flow():
    app = create_app()
    client = TestClient(app)
    _ingest_samples(client)

    run = handle_message({"tool": "run_evaluation", "arguments": {}})
    assert run["ok"] is True
    report_id = run["data"]["report_id"]
    assert run["data"]["summary"]["total_cases"] == 2

    listing = handle_message({"tool": "list_evaluation_reports", "arguments": {"limit": 10}})
    assert listing["ok"] is True
    assert listing["data"]
    assert listing["data"][0]["report_id"] == report_id

    detail = handle_message({"tool": "get_evaluation_report", "arguments": {"report_id": report_id}})
    assert detail["ok"] is True
    assert detail["data"]["report_id"] == report_id
    assert len(detail["data"]["cases"]) == 2


def test_dashboard_service_evaluation_flow():
    app = create_app()
    client = TestClient(app)
    _ingest_samples(client)

    service = DashboardService()
    report = service.run_evaluation()
    assert report["summary"]["total_cases"] == 2

    reports = service.list_evaluation_reports(limit=10)
    assert reports
    report_id = reports[0]["report_id"]

    detail = service.get_evaluation_report_detail(report_id)
    assert detail["report_id"] == report_id
    assert len(detail["cases"]) == 2
