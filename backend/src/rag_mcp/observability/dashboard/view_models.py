"""Dashboard-specific view model builders."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

FAILURE_STATUSES = {"error", "fallback"}


def build_document_overview(detail: dict) -> dict:
    """Project a document detail payload into a concise dashboard view."""
    metadata = detail.get("metadata", {})
    chunks = detail.get("chunks", [])
    chunk_lengths = [len(item.get("text", "")) for item in chunks]
    average_chunk_length = round(sum(chunk_lengths) / len(chunk_lengths), 2) if chunk_lengths else 0.0
    return {
        "document_id": detail.get("document_id"),
        "filename": detail.get("filename"),
        "doc_type": detail.get("doc_type"),
        "source_path": detail.get("source_path"),
        "chunk_count": detail.get("chunk_count", 0),
        "content_length": detail.get("content_length", 0),
        "average_chunk_length": average_chunk_length,
        "source_size_bytes": metadata.get("source_size_bytes", 0),
        "word_count": metadata.get("word_count", 0),
        "line_count": metadata.get("line_count", 0),
        "contains_cjk": metadata.get("contains_cjk", False),
        "loader_name": metadata.get("loader_name"),
        "source_modified_at": metadata.get("source_modified_at"),
        "image_asset_count": metadata.get("image_asset_count", 0),
        "multimodal_status": metadata.get("multimodal_status"),
    }


def metadata_rows(metadata: dict) -> list[dict]:
    """Flatten metadata into key-value rows for tabular display."""
    return [{"key": key, "value": value} for key, value in sorted(metadata.items(), key=lambda item: item[0])]


def build_trace_overview(detail: dict) -> dict:
    """Project a trace detail payload into a concise dashboard view."""
    stages = detail.get("stages", [])
    metadata = detail.get("metadata", {})
    stage_names = [stage.get("name") for stage in stages]
    first_stage = stages[0] if stages else {}
    idempotency_stage = _find_stage(stages, "idempotency_check")
    prompt_stage = _find_stage(stages, "prompt_build")
    llm_stage = _find_stage(stages, "llm_generate")
    rerank_stage = _find_stage(stages, "rerank")
    embedding_stage = _find_stage(stages, "embed_query")
    dense_stage = _find_stage(stages, "dense_retrieval")
    sparse_stage = _find_stage(stages, "sparse_retrieval")
    fusion_stage = _find_stage(stages, "fusion")
    aggregate_stage = _find_stage(stages, "aggregate_metrics")

    has_error = any(_stage_has_error(stage) for stage in stages)
    fallback_used = bool(llm_stage.get("data", {}).get("fallback")) if llm_stage else False
    ingestion_action = idempotency_stage.get("data", {}).get("ingestion_action") if idempotency_stage else None
    rerank_applied = bool(metadata.get("rerank_applied")) or rerank_stage is not None
    status = _derive_trace_status(
        trace_type=detail.get("trace_type"),
        has_error=has_error,
        fallback_used=fallback_used,
        ingestion_action=ingestion_action,
    )
    llm_provider = metadata.get("llm_provider") or _stage_value(llm_stage, "provider")
    llm_model = metadata.get("llm_model") or _stage_value(llm_stage, "model")
    embedding_provider = metadata.get("embedding_provider") or _stage_value(embedding_stage, "provider")
    rerank_provider = _stage_value(rerank_stage, "method")
    prompt_system_path = metadata.get("prompt_system_path") or _stage_value(prompt_stage, "system_prompt_path")
    prompt_user_path = metadata.get("prompt_user_path") or _stage_value(prompt_stage, "user_prompt_path")
    system_prompt_fingerprint = metadata.get("system_prompt_fingerprint") or _stage_value(
        prompt_stage,
        "system_prompt_fingerprint",
    )
    user_prompt_fingerprint = metadata.get("user_prompt_fingerprint") or _stage_value(
        prompt_stage,
        "user_prompt_fingerprint",
    )
    provider_label = _build_provider_label(
        trace_type=detail.get("trace_type"),
        llm_provider=llm_provider,
        llm_model=llm_model,
        embedding_provider=embedding_provider,
    )
    prompt_label = _build_prompt_label(
        prompt_user_path=prompt_user_path,
        user_prompt_fingerprint=user_prompt_fingerprint,
    )

    return {
        "trace_id": detail.get("trace_id"),
        "trace_type": detail.get("trace_type"),
        "status": status,
        "started_at": detail.get("started_at"),
        "finished_at": detail.get("finished_at"),
        "total_elapsed_ms": detail.get("total_elapsed_ms", 0.0),
        "stage_count": len(stages),
        "last_stage": stage_names[-1] if stage_names else None,
        "query": metadata.get("query"),
        "top_k": metadata.get("top_k"),
        "dataset_path": metadata.get("dataset_path"),
        "query_trace_id": metadata.get("query_trace_id"),
        "source_path": metadata.get("path") or metadata.get("source_path"),
        "document_id": metadata.get("document_id"),
        "ingestion_action": ingestion_action,
        "fallback_used": fallback_used,
        "rebuild": bool(metadata.get("rebuild")),
        "collection_name": metadata.get("collection_name"),
        "rerank_applied": rerank_applied,
        "generated_by_llm": bool(llm_stage) and not fallback_used,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "embedding_provider": embedding_provider,
        "rerank_provider": rerank_provider,
        "provider_label": provider_label,
        "source_count": _stage_int_value(prompt_stage, "source_count"),
        "prompt_system_path": prompt_system_path,
        "prompt_user_path": prompt_user_path,
        "prompt_label": prompt_label,
        "system_prompt_fingerprint": system_prompt_fingerprint,
        "user_prompt_fingerprint": user_prompt_fingerprint,
        "system_prompt_length": _stage_int_value(prompt_stage, "system_prompt_length"),
        "user_prompt_length": _stage_int_value(prompt_stage, "user_prompt_length"),
        "error_message": _first_error_message(stages),
        "source_size_bytes": first_stage.get("data", {}).get("source_size_bytes"),
        "dense_result_count": _stage_int_value(dense_stage, "result_count"),
        "sparse_result_count": _stage_int_value(sparse_stage, "result_count"),
        "fusion_result_count": _stage_int_value(fusion_stage, "result_count"),
        "rerank_result_count": _stage_int_value(rerank_stage, "result_count"),
        "evaluation_case_count": _stage_int_value(_find_stage(stages, "load_dataset"), "case_count"),
        "evaluation_hit_rate": _stage_value(aggregate_stage, "hit_rate"),
        "evaluation_mrr": _stage_value(aggregate_stage, "mrr"),
    }


def build_stage_timing_rows(stages: Iterable[dict]) -> list[dict]:
    """Add cumulative elapsed time for dashboard stage timing display."""
    cumulative_ms = 0.0
    rows: list[dict] = []
    for stage in stages:
        elapsed_ms = float(stage.get("elapsed_ms", 0.0))
        cumulative_ms += elapsed_ms
        rows.append(
            {
                "name": stage.get("name"),
                "elapsed_ms": elapsed_ms,
                "cumulative_ms": round(cumulative_ms, 2),
                "timestamp": stage.get("timestamp"),
                "has_error": _stage_has_error(stage),
                "data": stage.get("data", {}),
            }
        )
    return rows


def build_trace_summary(trace_overviews: list[dict]) -> dict:
    """Aggregate dashboard-friendly summary metrics from trace overviews."""
    status_counts = Counter(item.get("status", "unknown") for item in trace_overviews)
    type_counts = Counter(item.get("trace_type", "unknown") for item in trace_overviews)
    average_elapsed_ms = (
        round(sum(float(item.get("total_elapsed_ms", 0.0)) for item in trace_overviews) / len(trace_overviews), 2)
        if trace_overviews
        else 0.0
    )
    return {
        "total_traces": len(trace_overviews),
        "average_elapsed_ms": average_elapsed_ms,
        "status_counts": dict(sorted(status_counts.items())),
        "trace_type_counts": dict(sorted(type_counts.items())),
        "error_count": status_counts.get("error", 0),
        "fallback_count": status_counts.get("fallback", 0),
        "skipped_count": status_counts.get("skipped", 0),
        "replaced_count": status_counts.get("replaced", 0),
        "created_count": status_counts.get("created", 0),
        "ok_count": status_counts.get("ok", 0),
    }


def build_trace_detail_summary(detail: dict) -> dict:
    """Extract concise per-trace operational highlights for dashboard display."""
    overview = build_trace_overview(detail)
    metadata = detail.get("metadata", {})
    return {
        "trace_id": overview["trace_id"],
        "trace_type": overview["trace_type"],
        "status": overview["status"],
        "top_k": overview.get("top_k"),
        "query": overview.get("query"),
        "query_trace_id": overview.get("query_trace_id"),
        "dataset_path": overview.get("dataset_path"),
        "source_path": overview.get("source_path"),
        "document_id": overview.get("document_id"),
        "collection_name": overview.get("collection_name"),
        "ingestion_action": overview.get("ingestion_action"),
        "rebuild": overview.get("rebuild"),
        "generated_by_llm": overview.get("generated_by_llm"),
        "fallback_used": overview.get("fallback_used"),
        "llm_provider": overview.get("llm_provider"),
        "llm_model": overview.get("llm_model"),
        "embedding_provider": overview.get("embedding_provider"),
        "rerank_provider": overview.get("rerank_provider"),
        "provider_label": overview.get("provider_label"),
        "source_count": overview.get("source_count"),
        "prompt_system_path": overview.get("prompt_system_path"),
        "prompt_user_path": overview.get("prompt_user_path"),
        "prompt_label": overview.get("prompt_label"),
        "system_prompt_fingerprint": overview.get("system_prompt_fingerprint"),
        "user_prompt_fingerprint": overview.get("user_prompt_fingerprint"),
        "system_prompt_length": overview.get("system_prompt_length"),
        "user_prompt_length": overview.get("user_prompt_length"),
        "rerank_applied": overview.get("rerank_applied"),
        "dense_result_count": overview.get("dense_result_count"),
        "sparse_result_count": overview.get("sparse_result_count"),
        "fusion_result_count": overview.get("fusion_result_count"),
        "rerank_result_count": overview.get("rerank_result_count"),
        "evaluation_case_count": overview.get("evaluation_case_count"),
        "evaluation_hit_rate": overview.get("evaluation_hit_rate"),
        "evaluation_mrr": overview.get("evaluation_mrr"),
        "error_message": overview.get("error_message"),
        "metadata_keys": sorted(metadata.keys()),
    }


def build_failure_sample_rows(trace_overviews: list[dict]) -> list[dict]:
    """Return failure-like trace rows for troubleshooting views."""
    return [
        {
            "trace_id": item.get("trace_id"),
            "trace_type": item.get("trace_type"),
            "status": item.get("status"),
            "query": item.get("query"),
            "provider": item.get("provider_label"),
            "prompt": item.get("prompt_label"),
            "elapsed_ms": item.get("total_elapsed_ms", 0.0),
            "error_message": item.get("error_message"),
            "query_trace_id": item.get("query_trace_id"),
            "started_at": item.get("started_at"),
        }
        for item in trace_overviews
        if str(item.get("status")) in FAILURE_STATUSES
    ]


def build_failure_hotspot_rows(trace_overviews: list[dict], *, group_by: str) -> list[dict]:
    """Aggregate failure-like traces by query, provider, or prompt."""
    grouped: dict[str, dict] = {}
    for item in trace_overviews:
        if str(item.get("status")) not in FAILURE_STATUSES:
            continue
        label = _failure_group_label(item, group_by)
        bucket = grouped.setdefault(
            label,
            {
                "label": label,
                "trace_count": 0,
                "error_count": 0,
                "fallback_count": 0,
                "total_elapsed_ms": 0.0,
                "max_elapsed_ms": 0.0,
                "latest_started_at": item.get("started_at"),
                "latest_trace_id": item.get("trace_id"),
                "queries": set(),
                "providers": set(),
                "prompts": set(),
                "trace_types": set(),
                "sample_error": item.get("error_message"),
            },
        )
        elapsed_ms = float(item.get("total_elapsed_ms", 0.0))
        bucket["trace_count"] += 1
        bucket["total_elapsed_ms"] += elapsed_ms
        bucket["max_elapsed_ms"] = max(bucket["max_elapsed_ms"], elapsed_ms)
        bucket["error_count"] += 1 if item.get("status") == "error" else 0
        bucket["fallback_count"] += 1 if item.get("status") == "fallback" else 0
        bucket["queries"].add(item.get("query") or "(no query)")
        bucket["providers"].add(item.get("provider_label") or "(unknown provider)")
        bucket["prompts"].add(item.get("prompt_label") or "(no prompt)")
        bucket["trace_types"].add(item.get("trace_type") or "unknown")
        if (item.get("started_at") or "") >= (bucket["latest_started_at"] or ""):
            bucket["latest_started_at"] = item.get("started_at")
            bucket["latest_trace_id"] = item.get("trace_id")
        if not bucket["sample_error"] and item.get("error_message"):
            bucket["sample_error"] = item.get("error_message")

    rows: list[dict] = []
    for bucket in grouped.values():
        rows.append(
            {
                "label": bucket["label"],
                "trace_count": bucket["trace_count"],
                "error_count": bucket["error_count"],
                "fallback_count": bucket["fallback_count"],
                "average_elapsed_ms": round(
                    bucket["total_elapsed_ms"] / max(bucket["trace_count"], 1),
                    2,
                ),
                "max_elapsed_ms": round(bucket["max_elapsed_ms"], 2),
                "latest_started_at": bucket["latest_started_at"],
                "latest_trace_id": bucket["latest_trace_id"],
                "queries": _join_unique(bucket["queries"]),
                "providers": _join_unique(bucket["providers"]),
                "prompts": _join_unique(bucket["prompts"]),
                "trace_types": _join_unique(bucket["trace_types"]),
                "sample_error": bucket["sample_error"],
            }
        )
    rows.sort(
        key=lambda item: (
            item["error_count"] + item["fallback_count"],
            item["max_elapsed_ms"],
            item["label"],
        ),
        reverse=True,
    )
    return rows


def _find_stage(stages: list[dict], name: str) -> dict | None:
    for stage in stages:
        if stage.get("name") == name:
            return stage
    return None


def _stage_value(stage: dict | None, key: str):
    if stage is None:
        return None
    return stage.get("data", {}).get(key)


def _stage_int_value(stage: dict | None, key: str) -> int | None:
    value = _stage_value(stage, key)
    return int(value) if value is not None else None


def _stage_has_error(stage: dict) -> bool:
    if str(stage.get("name", "")).endswith("_failed"):
        return True
    data = stage.get("data", {})
    return "error" in data and bool(data["error"])


def _first_error_message(stages: list[dict]) -> str | None:
    for stage in stages:
        data = stage.get("data", {})
        if "error" in data and data["error"]:
            return str(data["error"])
        if str(stage.get("name", "")).endswith("_failed"):
            return str(data.get("error", stage.get("name")))
    return None


def _build_provider_label(
    *,
    trace_type: str | None,
    llm_provider: str | None,
    llm_model: str | None,
    embedding_provider: str | None,
) -> str | None:
    if trace_type == "answer_generation":
        return _format_provider_model(llm_provider, llm_model)
    if trace_type == "query":
        return embedding_provider
    return _format_provider_model(llm_provider, llm_model) or embedding_provider


def _build_prompt_label(
    *,
    prompt_user_path: str | None,
    user_prompt_fingerprint: str | None,
) -> str | None:
    if prompt_user_path and user_prompt_fingerprint:
        return f"{prompt_user_path}#{str(user_prompt_fingerprint)[:8]}"
    return prompt_user_path or user_prompt_fingerprint


def _format_provider_model(provider: str | None, model: str | None) -> str | None:
    if provider and model:
        return f"{provider} / {model}"
    return provider or model


def _failure_group_label(item: dict, group_by: str) -> str:
    if group_by == "query":
        return str(item.get("query") or "(no query)")
    if group_by == "provider":
        return str(item.get("provider_label") or "(unknown provider)")
    if group_by == "prompt":
        return str(item.get("prompt_label") or "(no prompt)")
    raise ValueError(f"Unsupported failure hotspot grouping: {group_by}")


def _join_unique(values: Iterable[str], limit: int = 3) -> str:
    normalized = sorted({str(item) for item in values if item not in (None, "", "None")})
    if not normalized:
        return ""
    if len(normalized) <= limit:
        return " | ".join(normalized)
    return " | ".join(normalized[:limit]) + f" | +{len(normalized) - limit} more"


def _derive_trace_status(
    *,
    trace_type: str | None,
    has_error: bool,
    fallback_used: bool,
    ingestion_action: str | None,
) -> str:
    if fallback_used:
        return "fallback"
    if has_error:
        return "error"
    if trace_type == "ingestion" and ingestion_action:
        return ingestion_action
    return "ok"
