from rag_mcp.observability.dashboard.view_models import (
    build_document_overview,
    build_failure_hotspot_rows,
    build_failure_sample_rows,
    build_trace_detail_summary,
    build_stage_timing_rows,
    build_trace_overview,
    build_trace_summary,
    metadata_rows,
)


def test_build_document_overview_projects_key_metrics():
    detail = {
        "document_id": "doc-1",
        "filename": "sample.md",
        "doc_type": "md",
        "source_path": "sample.md",
        "chunk_count": 2,
        "content_length": 120,
        "metadata": {
            "source_size_bytes": 64,
            "word_count": 18,
            "line_count": 3,
            "contains_cjk": True,
            "loader_name": "TextDocumentLoader",
            "source_modified_at": "2026-05-18T00:00:00+00:00",
            "image_asset_count": 0,
            "multimodal_status": "skeleton_only",
        },
        "chunks": [{"text": "alpha beta"}, {"text": "gamma delta epsilon"}],
    }

    overview = build_document_overview(detail)

    assert overview["document_id"] == "doc-1"
    assert overview["chunk_count"] == 2
    assert overview["source_size_bytes"] == 64
    assert overview["contains_cjk"] is True
    assert overview["image_asset_count"] == 0
    assert overview["multimodal_status"] == "skeleton_only"
    assert overview["average_chunk_length"] > 0


def test_build_trace_overview_marks_ingestion_skip_and_answer_fallback():
    ingestion_detail = {
        "trace_id": "trace-1",
        "trace_type": "ingestion",
        "started_at": "2026-05-18T00:00:00+00:00",
        "finished_at": "2026-05-18T00:00:01+00:00",
        "total_elapsed_ms": 10.0,
        "metadata": {"path": "sample.md"},
        "stages": [
            {"name": "precheck", "elapsed_ms": 1.0, "timestamp": "t1", "data": {"source_size_bytes": 64}},
            {
                "name": "idempotency_check",
                "elapsed_ms": 0.0,
                "timestamp": "t2",
                "data": {"ingestion_action": "skipped", "reason": "precheck_unchanged_source"},
            },
        ],
    }
    answer_detail = {
        "trace_id": "trace-2",
        "trace_type": "answer_generation",
        "started_at": "2026-05-18T00:00:00+00:00",
        "finished_at": "2026-05-18T00:00:01+00:00",
        "total_elapsed_ms": 20.0,
        "metadata": {
            "query": "what is supported?",
            "top_k": 3,
            "query_trace_id": "trace-query-1",
            "rerank_applied": True,
            "llm_provider": "StubLlmProvider",
            "llm_model": "stub",
            "prompt_system_path": "config/prompts/answer_system.txt",
            "prompt_user_path": "config/prompts/answer_user.txt",
        },
        "stages": [
            {
                "name": "prompt_build",
                "elapsed_ms": 1.0,
                "timestamp": "t1",
                "data": {
                    "source_count": 2,
                    "system_prompt_path": "config/prompts/answer_system.txt",
                    "user_prompt_path": "config/prompts/answer_user.txt",
                    "system_prompt_fingerprint": "abc123def4567890",
                    "user_prompt_fingerprint": "fedcba0987654321",
                    "system_prompt_length": 20,
                    "user_prompt_length": 120,
                },
            },
            {
                "name": "llm_generate",
                "elapsed_ms": 5.0,
                "timestamp": "t2",
                "data": {"provider": "Stub", "model": "stub", "fallback": True, "error": "provider failed"},
            },
        ],
    }

    ingestion_overview = build_trace_overview(ingestion_detail)
    answer_overview = build_trace_overview(answer_detail)

    assert ingestion_overview["status"] == "skipped"
    assert ingestion_overview["ingestion_action"] == "skipped"
    assert answer_overview["status"] == "fallback"
    assert answer_overview["fallback_used"] is True
    assert answer_overview["generated_by_llm"] is False
    assert answer_overview["error_message"] == "provider failed"
    assert answer_overview["query_trace_id"] == "trace-query-1"
    assert answer_overview["rerank_applied"] is True
    assert answer_overview["llm_provider"] == "StubLlmProvider"
    assert answer_overview["llm_model"] == "stub"
    assert answer_overview["source_count"] == 2
    assert answer_overview["prompt_system_path"] == "config/prompts/answer_system.txt"
    assert answer_overview["prompt_user_path"] == "config/prompts/answer_user.txt"
    assert answer_overview["system_prompt_fingerprint"] == "abc123def4567890"
    assert answer_overview["user_prompt_fingerprint"] == "fedcba0987654321"


def test_build_stage_timing_rows_and_metadata_rows():
    stages = [
        {"name": "load", "elapsed_ms": 1.5, "timestamp": "t1", "data": {"filename": "sample.md"}},
        {"name": "embed", "elapsed_ms": 2.5, "timestamp": "t2", "data": {}},
    ]

    rows = build_stage_timing_rows(stages)
    flat_metadata = metadata_rows({"b": 2, "a": 1})

    assert rows[0]["cumulative_ms"] == 1.5
    assert rows[1]["cumulative_ms"] == 4.0
    assert flat_metadata[0]["key"] == "a"


def test_build_trace_summary_and_detail_summary_extract_operational_signals():
    query_detail = {
        "trace_id": "trace-query",
        "trace_type": "query",
        "started_at": "2026-05-18T00:00:00+00:00",
        "finished_at": "2026-05-18T00:00:01+00:00",
        "total_elapsed_ms": 12.5,
        "metadata": {"query": "dense retrieval", "top_k": 2},
        "stages": [
            {"name": "embed_query", "elapsed_ms": 1.0, "timestamp": "t1", "data": {"provider": "HashEmbeddingProvider"}},
            {"name": "dense_retrieval", "elapsed_ms": 2.0, "timestamp": "t2", "data": {"result_count": 3}},
            {"name": "sparse_retrieval", "elapsed_ms": 2.0, "timestamp": "t3", "data": {"result_count": 2}},
            {"name": "fusion", "elapsed_ms": 1.0, "timestamp": "t4", "data": {"result_count": 2, "method": "rrf"}},
            {"name": "rerank", "elapsed_ms": 1.0, "timestamp": "t5", "data": {"result_count": 2, "method": "LexicalReranker"}},
        ],
    }
    answer_detail = {
        "trace_id": "trace-answer",
        "trace_type": "answer_generation",
        "started_at": "2026-05-18T00:00:00+00:00",
        "finished_at": "2026-05-18T00:00:01+00:00",
        "total_elapsed_ms": 20.0,
        "metadata": {
            "query": "what is supported?",
            "top_k": 3,
            "query_trace_id": "trace-query",
            "rerank_applied": True,
            "llm_provider": "StubLlmProvider",
            "llm_model": "stub",
            "prompt_system_path": "config/prompts/answer_system.txt",
            "prompt_user_path": "config/prompts/answer_user.txt",
        },
        "stages": [
            {
                "name": "prompt_build",
                "elapsed_ms": 1.0,
                "timestamp": "t1",
                "data": {
                    "source_count": 2,
                    "system_prompt_path": "config/prompts/answer_system.txt",
                    "user_prompt_path": "config/prompts/answer_user.txt",
                    "system_prompt_fingerprint": "abc123def4567890",
                    "user_prompt_fingerprint": "fedcba0987654321",
                    "system_prompt_length": 20,
                    "user_prompt_length": 120,
                },
            },
            {
                "name": "llm_generate",
                "elapsed_ms": 5.0,
                "timestamp": "t2",
                "data": {"provider": "Stub", "model": "stub", "fallback": True, "error": "provider failed"},
            },
        ],
    }

    overviews = [build_trace_overview(query_detail), build_trace_overview(answer_detail)]
    summary = build_trace_summary(overviews)
    detail_summary = build_trace_detail_summary(answer_detail)

    assert summary["total_traces"] == 2
    assert summary["fallback_count"] == 1
    assert summary["ok_count"] == 1
    assert detail_summary["top_k"] == 3
    assert detail_summary["query_trace_id"] == "trace-query"
    assert detail_summary["llm_provider"] == "StubLlmProvider"
    assert detail_summary["llm_model"] == "stub"
    assert detail_summary["source_count"] == 2
    assert detail_summary["prompt_system_path"] == "config/prompts/answer_system.txt"
    assert detail_summary["prompt_user_path"] == "config/prompts/answer_user.txt"
    assert detail_summary["system_prompt_fingerprint"] == "abc123def4567890"
    assert detail_summary["user_prompt_fingerprint"] == "fedcba0987654321"
    assert detail_summary["system_prompt_length"] == 20
    assert detail_summary["user_prompt_length"] == 120
    assert detail_summary["rerank_applied"] is True
    assert detail_summary["provider_label"] == "StubLlmProvider / stub"
    assert detail_summary["prompt_label"] == "config/prompts/answer_user.txt#fedcba09"


def test_build_failure_views_group_by_query_provider_and_prompt():
    query_error = build_trace_overview(
        {
            "trace_id": "trace-query-error",
            "trace_type": "query",
            "started_at": "2026-05-18T00:00:00+00:00",
            "finished_at": "2026-05-18T00:00:01+00:00",
            "total_elapsed_ms": 11.0,
            "metadata": {"query": "dense retrieval", "top_k": 2},
            "stages": [
                {
                    "name": "embed_query",
                    "elapsed_ms": 1.0,
                    "timestamp": "t1",
                    "data": {"provider": "HashEmbeddingProvider"},
                },
                {
                    "name": "dense_retrieval_failed",
                    "elapsed_ms": 5.0,
                    "timestamp": "t2",
                    "data": {"error": "vector store timeout"},
                },
            ],
        }
    )
    answer_fallback_a = build_trace_overview(
        {
            "trace_id": "trace-answer-a",
            "trace_type": "answer_generation",
            "started_at": "2026-05-18T00:00:02+00:00",
            "finished_at": "2026-05-18T00:00:03+00:00",
            "total_elapsed_ms": 21.0,
            "metadata": {
                "query": "what is supported?",
                "top_k": 3,
                "query_trace_id": "trace-query-a",
                "llm_provider": "StubLlmProvider",
                "llm_model": "stub",
                "prompt_user_path": "config/prompts/answer_user.txt",
            },
            "stages": [
                {
                    "name": "prompt_build",
                    "elapsed_ms": 1.0,
                    "timestamp": "t1",
                    "data": {
                        "user_prompt_path": "config/prompts/answer_user.txt",
                        "user_prompt_fingerprint": "fedcba0987654321",
                    },
                },
                {
                    "name": "llm_generate",
                    "elapsed_ms": 6.0,
                    "timestamp": "t2",
                    "data": {
                        "provider": "StubLlmProvider",
                        "model": "stub",
                        "fallback": True,
                        "error": "provider failed",
                    },
                },
            ],
        }
    )
    answer_fallback_b = build_trace_overview(
        {
            "trace_id": "trace-answer-b",
            "trace_type": "answer_generation",
            "started_at": "2026-05-18T00:00:04+00:00",
            "finished_at": "2026-05-18T00:00:05+00:00",
            "total_elapsed_ms": 25.0,
            "metadata": {
                "query": "what is supported?",
                "top_k": 3,
                "query_trace_id": "trace-query-b",
                "llm_provider": "StubLlmProvider",
                "llm_model": "stub",
                "prompt_user_path": "config/prompts/answer_user.txt",
            },
            "stages": [
                {
                    "name": "prompt_build",
                    "elapsed_ms": 1.0,
                    "timestamp": "t1",
                    "data": {
                        "user_prompt_path": "config/prompts/answer_user.txt",
                        "user_prompt_fingerprint": "fedcba0987654321",
                    },
                },
                {
                    "name": "llm_generate",
                    "elapsed_ms": 8.0,
                    "timestamp": "t2",
                    "data": {
                        "provider": "StubLlmProvider",
                        "model": "stub",
                        "fallback": True,
                        "error": "provider failed again",
                    },
                },
            ],
        }
    )

    overviews = [query_error, answer_fallback_a, answer_fallback_b]
    failure_samples = build_failure_sample_rows(overviews)
    by_query = build_failure_hotspot_rows(overviews, group_by="query")
    by_provider = build_failure_hotspot_rows(overviews, group_by="provider")
    by_prompt = build_failure_hotspot_rows(overviews, group_by="prompt")

    assert len(failure_samples) == 3
    assert any(item["status"] == "error" for item in failure_samples)
    assert any(item["status"] == "fallback" for item in failure_samples)

    query_row = next(item for item in by_query if item["label"] == "what is supported?")
    assert query_row["trace_count"] == 2
    assert query_row["fallback_count"] == 2

    provider_row = next(item for item in by_provider if item["label"] == "StubLlmProvider / stub")
    assert provider_row["trace_count"] == 2
    assert provider_row["fallback_count"] == 2

    prompt_row = next(item for item in by_prompt if item["label"] == "config/prompts/answer_user.txt#fedcba09")
    assert prompt_row["trace_count"] == 2
    assert prompt_row["fallback_count"] == 2
