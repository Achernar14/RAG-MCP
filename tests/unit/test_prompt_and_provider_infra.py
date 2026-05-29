import json
from pathlib import Path

import pytest
import yaml

from rag_mcp.application.dto.models import (
    GenerateAnswerRequest,
    QueryResponse,
    QueryResultDto,
    QuerySourceDto,
)
from rag_mcp.application.use_cases.generate_answer import GenerateAnswerUseCase
from rag_mcp.core.exceptions import ConfigurationError, ProviderError
from rag_mcp.core.settings import load_settings
from rag_mcp.core.tracing import JsonlTraceCollector
from rag_mcp.infrastructure.llm.stub_llm import StubLlmProvider
from rag_mcp.infrastructure.prompts.answer_prompt_builder import AnswerPromptBuilder
from rag_mcp.infrastructure.prompts.template_loader import (
    FilePromptTemplateLoader,
    StaticPromptTemplateLoader,
)
from rag_mcp.infrastructure.providers.factories import (
    create_embedding_provider,
    create_llm_provider,
    create_reranker,
    create_vision_llm_provider,
)


class _FakeQueryUseCase:
    def execute(self, request):
        return QueryResponse(
            query=request.query,
            results=[
                QueryResultDto(
                    chunk_id="chunk-1",
                    score=0.9,
                    text="MVP supports ingestion and retrieval.",
                    source_path="sample.md",
                    retrieval_method="hybrid_rerank",
                )
            ],
            sources=[
                QuerySourceDto(
                    index=1,
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    source_path="sample.md",
                    score=0.9,
                    snippet="MVP supports ingestion and retrieval.",
                    chunk_index=0,
                )
            ],
            trace_id="trace-query",
            rerank_applied=True,
        )


class _FailingLlmProvider:
    model = "failing-test-model"

    def generate(self, prompt: str, *, system_prompt: str | None = None, metadata: dict | None = None) -> str:
        del prompt, system_prompt, metadata
        raise ProviderError("simulated provider failure")


def _write_settings(tmp_path: Path, payload: dict) -> Path:
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return settings_path


def test_file_prompt_template_loader_reads_utf8_files(tmp_path):
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("hello {name}", encoding="utf-8")

    loader = FilePromptTemplateLoader()
    content = loader.load(str(prompt_path))

    assert content == "hello {name}"


def test_answer_prompt_builder_renders_sources():
    builder = AnswerPromptBuilder(
        template_loader=StaticPromptTemplateLoader(
            {
                "system": "System guardrails.",
                "user": "Question: {query}\nSources:\n{sources}",
            }
        ),
        system_prompt_path="system",
        user_prompt_path="user",
    )

    rendered = builder.build(
        query="What is supported?",
        source_items=[
            {"index": 1, "source_path": "sample.md", "snippet": "Supports ingestion."},
            {"index": 2, "source_path": "bm25.md", "snippet": "Supports BM25."},
        ],
    )

    assert rendered.system_prompt == "System guardrails."
    assert "What is supported?" in rendered.user_prompt
    assert "[1] sample.md :: Supports ingestion." in rendered.user_prompt
    assert "[2] bm25.md :: Supports BM25." in rendered.user_prompt
    assert rendered.system_prompt_path == "system"
    assert rendered.user_prompt_path == "user"
    assert len(rendered.system_prompt_fingerprint) == 16
    assert len(rendered.user_prompt_fingerprint) == 16
    assert rendered.system_prompt_length == len(rendered.system_prompt)
    assert rendered.user_prompt_length == len(rendered.user_prompt)


def test_generate_answer_use_case_falls_back_when_llm_fails(tmp_path):
    builder = AnswerPromptBuilder(
        template_loader=StaticPromptTemplateLoader(
            {
                "system": "System guardrails.",
                "user": "Question: {query}\nSources:\n{sources}",
            }
        ),
        system_prompt_path="system",
        user_prompt_path="user",
    )
    collector = JsonlTraceCollector(tmp_path / "traces.jsonl")
    use_case = GenerateAnswerUseCase(
        query_use_case=_FakeQueryUseCase(),
        llm_provider=_FailingLlmProvider(),
        trace_collector=collector,
        answer_prompt_builder=builder,
    )

    response = use_case.execute(GenerateAnswerRequest(query="What is supported?", top_k=3))

    assert response.generated_by_llm is False
    assert response.generation_error == "simulated provider failure"
    assert "降级回答" in response.answer
    assert response.sources


    traces = (tmp_path / "traces.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert traces
    persisted = json.loads(traces[-1])
    prompt_stage = next(stage for stage in persisted["stages"] if stage["name"] == "prompt_build")
    llm_stage = next(stage for stage in persisted["stages"] if stage["name"] == "llm_generate")

    assert persisted["metadata"]["query_trace_id"] == "trace-query"
    assert persisted["metadata"]["rerank_applied"] is True
    assert persisted["metadata"]["llm_provider"] == "_FailingLlmProvider"
    assert persisted["metadata"]["llm_model"] == "failing-test-model"
    assert persisted["metadata"]["prompt_system_path"] == "system"
    assert persisted["metadata"]["prompt_user_path"] == "user"
    assert prompt_stage["data"]["source_count"] == 1
    assert prompt_stage["data"]["query_trace_id"] == "trace-query"
    assert prompt_stage["data"]["system_prompt_path"] == "system"
    assert prompt_stage["data"]["user_prompt_path"] == "user"
    assert len(prompt_stage["data"]["system_prompt_fingerprint"]) == 16
    assert len(prompt_stage["data"]["user_prompt_fingerprint"]) == 16
    assert prompt_stage["data"]["system_prompt_length"] > 0
    assert prompt_stage["data"]["user_prompt_length"] > 0
    assert llm_stage["data"]["provider"] == "_FailingLlmProvider"
    assert llm_stage["data"]["model"] == "failing-test-model"
    assert llm_stage["data"]["fallback"] is True
    assert llm_stage["data"]["source_count"] == 1


def test_create_providers_from_settings(tmp_path, monkeypatch):
    payload = {
        "embedding": {"provider": "hash", "dimensions": 32},
        "embedding_provider": {
            "api_base": None,
            "api_key_env": "ZHIPU_API_KEY",
            "model": None,
            "timeout_seconds": 30.0,
        },
        "llm": {
            "provider": "stub",
            "enabled": False,
            "api_base": None,
            "api_key_env": "DEEPSEEK_API_KEY",
            "model": None,
            "temperature": 0.1,
            "max_tokens": 128,
            "timeout_seconds": 60.0,
        },
        "vision_llm": {"provider": "disabled", "enabled": False},
        "vector_store": {"provider": "memory", "persist_path": "data/vector_store/weaviate"},
        "ingestion": {
            "chunk_size": 200,
            "chunk_overlap": 20,
            "normalize_whitespace": True,
            "preserve_paragraph_breaks": True,
            "boundary_scan_chars": 40,
            "min_chunk_length": 20,
            "supported_extensions": [".md"],
        },
        "retrieval": {"top_k": 5, "dense_top_k": 5, "sparse_top_k": 5, "hybrid_top_k": 5, "rrf_k": 60, "rerank_enabled": True, "rerank_top_k": 5},
        "rerank": {"provider": "lexical", "enabled": True},
        "observability": {"trace_enabled": True, "trace_path": "data/traces/traces.jsonl"},
        "evaluation": {"enabled": True, "report_path": "data/evaluations/reports.jsonl", "default_test_set_path": "data/evaluations/golden_test_set.json"},
        "prompts": {"answer_system_prompt_path": "config/prompts/answer_system.txt", "answer_user_prompt_path": "config/prompts/answer_user.txt"},
        "mcp": {"server_name": "rag-mcp", "server_version": "0.1.0"},
        "api": {"host": "127.0.0.1", "port": 8000},
    }
    settings_path = _write_settings(tmp_path, payload)
    monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))

    settings = load_settings()
    embedding_provider = create_embedding_provider(settings)
    llm_provider = create_llm_provider(settings)

    assert embedding_provider.__class__.__name__ == "HashEmbeddingProvider"
    assert isinstance(llm_provider, StubLlmProvider)


def test_create_provider_raises_for_unknown_embedding_provider(tmp_path, monkeypatch):
    payload = {
        "embedding": {"provider": "unknown", "dimensions": 32},
        "embedding_provider": {},
        "llm": {"provider": "stub", "enabled": False},
        "vision_llm": {"provider": "disabled", "enabled": False},
        "vector_store": {"provider": "memory", "persist_path": "data/vector_store/weaviate"},
        "ingestion": {
            "chunk_size": 200,
            "chunk_overlap": 20,
            "normalize_whitespace": True,
            "preserve_paragraph_breaks": True,
            "boundary_scan_chars": 40,
            "min_chunk_length": 20,
            "supported_extensions": [".md"],
        },
        "retrieval": {"top_k": 5, "dense_top_k": 5, "sparse_top_k": 5, "hybrid_top_k": 5, "rrf_k": 60, "rerank_enabled": True, "rerank_top_k": 5},
        "rerank": {"provider": "lexical", "enabled": True},
        "observability": {"trace_enabled": True, "trace_path": "data/traces/traces.jsonl"},
        "evaluation": {"enabled": True, "report_path": "data/evaluations/reports.jsonl", "default_test_set_path": "data/evaluations/golden_test_set.json"},
        "prompts": {"answer_system_prompt_path": "config/prompts/answer_system.txt", "answer_user_prompt_path": "config/prompts/answer_user.txt"},
        "mcp": {"server_name": "rag-mcp", "server_version": "0.1.0"},
        "api": {"host": "127.0.0.1", "port": 8000},
    }
    settings_path = _write_settings(tmp_path, payload)
    monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))

    settings = load_settings()
    with pytest.raises(ConfigurationError):
        create_embedding_provider(settings)


def test_create_reranker_and_vision_provider_from_settings(tmp_path, monkeypatch):
    payload = {
        "embedding": {"provider": "hash", "dimensions": 32},
        "embedding_provider": {},
        "llm": {"provider": "stub", "enabled": False},
        "vision_llm": {"provider": "disabled", "enabled": False},
        "vector_store": {"provider": "memory", "persist_path": "data/vector_store/weaviate"},
        "ingestion": {
            "chunk_size": 200,
            "chunk_overlap": 20,
            "normalize_whitespace": True,
            "preserve_paragraph_breaks": True,
            "boundary_scan_chars": 40,
            "min_chunk_length": 20,
            "supported_extensions": [".md"],
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
        "rerank": {"provider": "lexical", "enabled": True},
        "observability": {"trace_enabled": True, "trace_path": "data/traces/traces.jsonl"},
        "evaluation": {"enabled": True, "report_path": "data/evaluations/reports.jsonl", "default_test_set_path": "data/evaluations/golden_test_set.json"},
        "prompts": {"answer_system_prompt_path": "config/prompts/answer_system.txt", "answer_user_prompt_path": "config/prompts/answer_user.txt"},
        "mcp": {"server_name": "rag-mcp", "server_version": "0.1.0"},
        "api": {"host": "127.0.0.1", "port": 8000},
    }
    settings_path = _write_settings(tmp_path, payload)
    monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))

    settings = load_settings()
    reranker = create_reranker(settings)
    vision_provider = create_vision_llm_provider(settings)

    assert reranker.__class__.__name__ == "LexicalReranker"
    assert vision_provider is None


def test_create_reranker_returns_none_when_disabled(tmp_path, monkeypatch):
    payload = {
        "embedding": {"provider": "hash", "dimensions": 32},
        "embedding_provider": {},
        "llm": {"provider": "stub", "enabled": False},
        "vision_llm": {"provider": "disabled", "enabled": False},
        "vector_store": {"provider": "memory", "persist_path": "data/vector_store/weaviate"},
        "ingestion": {
            "chunk_size": 200,
            "chunk_overlap": 20,
            "normalize_whitespace": True,
            "preserve_paragraph_breaks": True,
            "boundary_scan_chars": 40,
            "min_chunk_length": 20,
            "supported_extensions": [".md"],
        },
        "retrieval": {
            "top_k": 5,
            "dense_top_k": 5,
            "sparse_top_k": 5,
            "hybrid_top_k": 5,
            "rrf_k": 60,
            "rerank_enabled": False,
            "rerank_top_k": 5,
        },
        "rerank": {"provider": "lexical", "enabled": True},
        "observability": {"trace_enabled": True, "trace_path": "data/traces/traces.jsonl"},
        "evaluation": {"enabled": True, "report_path": "data/evaluations/reports.jsonl", "default_test_set_path": "data/evaluations/golden_test_set.json"},
        "prompts": {"answer_system_prompt_path": "config/prompts/answer_system.txt", "answer_user_prompt_path": "config/prompts/answer_user.txt"},
        "mcp": {"server_name": "rag-mcp", "server_version": "0.1.0"},
        "api": {"host": "127.0.0.1", "port": 8000},
    }
    settings_path = _write_settings(tmp_path, payload)
    monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))

    settings = load_settings()
    reranker = create_reranker(settings)

    assert reranker is None


def test_create_reranker_raises_for_unknown_provider(tmp_path, monkeypatch):
    payload = {
        "embedding": {"provider": "hash", "dimensions": 32},
        "embedding_provider": {},
        "llm": {"provider": "stub", "enabled": False},
        "vision_llm": {"provider": "disabled", "enabled": False},
        "vector_store": {"provider": "memory", "persist_path": "data/vector_store/weaviate"},
        "ingestion": {
            "chunk_size": 200,
            "chunk_overlap": 20,
            "normalize_whitespace": True,
            "preserve_paragraph_breaks": True,
            "boundary_scan_chars": 40,
            "min_chunk_length": 20,
            "supported_extensions": [".md"],
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
        "rerank": {"provider": "cross-encoder", "enabled": True},
        "observability": {"trace_enabled": True, "trace_path": "data/traces/traces.jsonl"},
        "evaluation": {"enabled": True, "report_path": "data/evaluations/reports.jsonl", "default_test_set_path": "data/evaluations/golden_test_set.json"},
        "prompts": {"answer_system_prompt_path": "config/prompts/answer_system.txt", "answer_user_prompt_path": "config/prompts/answer_user.txt"},
        "mcp": {"server_name": "rag-mcp", "server_version": "0.1.0"},
        "api": {"host": "127.0.0.1", "port": 8000},
    }
    settings_path = _write_settings(tmp_path, payload)
    monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))

    settings = load_settings()
    with pytest.raises(ConfigurationError):
        create_reranker(settings)
