from pathlib import Path

import pytest
import yaml

from rag_mcp.core.container import reset_container
from rag_mcp.observability.dashboard.services import DashboardService


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


def test_dashboard_service_exposes_management_and_trace_data():
    from rag_mcp.core.container import get_container
    from rag_mcp.application.dto.models import GenerateAnswerRequest
    from rag_mcp.application.dto.models import IngestRequest
    from rag_mcp.application.dto.models import QueryRequest

    sample_path = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"
    container = get_container()

    ingest = container.ingest_use_case.execute(IngestRequest(path=str(sample_path)))
    query = container.query_use_case.execute(QueryRequest(query="dense retrieval", top_k=2))
    answer = container.generate_answer_use_case.execute(
        GenerateAnswerRequest(query="What does the MVP support?", top_k=2)
    )

    service = DashboardService()
    settings = service.get_settings()
    assert settings["vector_store"]["collection_name"] == "TestRAGMCP"

    status = service.get_status()
    assert status["document_count"] >= 1
    assert status["chunk_count"] >= 1

    collections = service.list_collections()
    assert collections
    assert collections[0]["name"] == "TestRAGMCP"

    documents = service.list_documents()
    assert documents
    document_id = documents[0]["id"]

    detail = service.get_document_detail(document_id)
    assert detail["document_id"] == document_id
    assert detail["chunks"]

    overview = service.get_document_overview(document_id)
    assert overview["document_id"] == document_id
    assert overview["chunk_count"] >= 1
    assert overview["word_count"] >= 1

    traces = service.list_traces(limit=10)
    assert {item["trace_id"] for item in traces} >= {ingest.trace_id, query.trace_id, answer.trace_id}

    trace_overview = service.list_trace_overview(limit=10)
    trace_ids = {item["trace_id"] for item in trace_overview}
    assert {ingest.trace_id, query.trace_id, answer.trace_id} <= trace_ids
    assert any(item["trace_type"] == "answer_generation" for item in trace_overview)
    query_overview = next(item for item in trace_overview if item["trace_id"] == query.trace_id)
    assert query_overview["top_k"] == 2

    trace_detail = service.get_trace_detail(query.trace_id)
    assert trace_detail["trace_id"] == query.trace_id
    assert trace_detail["stages"]

    trace_summary = service.get_trace_summary(limit=10)
    assert trace_summary["total_traces"] >= 3
    assert trace_summary["trace_type_counts"]["query"] >= 1

    detail_summary = service.get_trace_detail_summary(answer.trace_id)
    assert detail_summary["trace_type"] == "answer_generation"
    assert detail_summary["query"] == "What does the MVP support?"
    assert detail_summary["query_trace_id"]
    assert detail_summary["llm_provider"] == "StubLlmProvider"
    assert detail_summary["llm_model"] == "stub"
    assert detail_summary["provider_label"] == "StubLlmProvider / stub"
    assert detail_summary["prompt_system_path"] == "config/prompts/answer_system.txt"
    assert detail_summary["prompt_user_path"] == "config/prompts/answer_user.txt"
    assert detail_summary["prompt_label"].startswith("config/prompts/answer_user.txt#")
    assert detail_summary["source_count"] >= 1
    assert detail_summary["system_prompt_fingerprint"]
    assert detail_summary["user_prompt_fingerprint"]

    navigation = service.get_trace_navigation_context(answer.trace_id)
    assert navigation["selected"]["trace_id"] == answer.trace_id
    assert navigation["linked_query"] is not None
    assert navigation["linked_query"]["trace_id"] == detail_summary["query_trace_id"]

    query_navigation = service.get_trace_navigation_context(detail_summary["query_trace_id"])
    assert query_navigation["selected"]["trace_type"] == "query"
    assert any(item["trace_id"] == answer.trace_id for item in query_navigation["related_answers"])


def test_dashboard_service_exposes_mutating_management_actions(tmp_path):
    sample_path = tmp_path / "dashboard_action.md"
    sample_path.write_text("dashboard action content", encoding="utf-8")

    service = DashboardService()
    ingest = service.ingest_document(str(sample_path))
    assert ingest["chunk_count"] >= 1

    documents = service.list_documents()
    assert documents
    document_id = documents[0]["id"]

    rebuild = service.rebuild_collection("TestRAGMCP")
    assert rebuild["requested_document_count"] >= 1
    assert rebuild["rebuilt_document_count"] >= 1

    deletion = service.delete_document(document_id)
    assert deletion["document_id"] == document_id
    assert deletion["deleted_chunk_count"] >= 1

    remaining = service.list_documents()
    assert all(item["id"] != document_id for item in remaining)
