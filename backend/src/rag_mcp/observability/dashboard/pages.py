"""Dashboard page renderers."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from rag_mcp.core.exceptions import NotFoundError
from rag_mcp.observability.dashboard.services import DashboardService
from rag_mcp.observability.dashboard.view_models import (
    build_failure_hotspot_rows,
    build_failure_sample_rows,
    build_stage_timing_rows,
    metadata_rows,
)


def render_overview_page() -> None:
    """Render the dashboard overview page."""
    service = DashboardService()
    status = service.get_status()
    collections = service.list_collections()
    reports = service.list_evaluation_reports(limit=1)
    recent_operations = service.list_trace_overview(limit=8)
    recent_summary = service.get_trace_summary(limit=20)
    settings = service.get_settings()

    st.title("RAG MCP Overview")
    metric_a, metric_b, metric_c, metric_d = st.columns(4)
    metric_a.metric("Documents", status["document_count"])
    metric_b.metric("Chunks", status["chunk_count"])
    metric_c.metric("Collection", status["collection_name"])
    metric_d.metric("Eval Reports", len(reports))

    summary_a, summary_b, summary_c, summary_d = st.columns(4)
    summary_a.metric("Recent Traces", recent_summary["total_traces"])
    summary_b.metric("Errors", recent_summary["error_count"])
    summary_c.metric("Fallbacks", recent_summary["fallback_count"])
    summary_d.metric("Avg Trace ms", recent_summary["average_elapsed_ms"])

    st.subheader("Recent Trace Status Summary")
    st.dataframe(
        [
            {"status": status_name, "count": count}
            for status_name, count in recent_summary["status_counts"].items()
        ],
        use_container_width=True,
    )

    st.subheader("Collection Status")
    st.dataframe(collections, use_container_width=True)

    st.subheader("Runtime Settings")
    st.json(
        {
            "app": settings["app"],
            "vector_store": settings["vector_store"],
            "retrieval": settings["retrieval"],
            "observability": settings["observability"],
        },
        expanded=False,
    )

    st.subheader("Recent Operations")
    if recent_operations:
        st.dataframe(
            [
                {
                    "trace_type": item["trace_type"],
                    "status": item["status"],
                    "started_at": item["started_at"],
                    "elapsed_ms": item["total_elapsed_ms"],
                    "query": item["query"],
                    "provider": item.get("provider_label"),
                    "prompt": item.get("prompt_label"),
                    "source_path": item["source_path"],
                    "dataset_path": item["dataset_path"],
                }
                for item in recent_operations
            ],
            use_container_width=True,
        )
    else:
        st.info("No recent operations available yet.")


def render_documents_page() -> None:
    """Render the document browser page."""
    service = DashboardService()
    documents = service.list_documents()

    st.title("Documents")
    if not documents:
        st.info("No documents have been ingested yet.")
        return

    search_term = st.text_input("Search filename or path", placeholder="sample.md")
    available_types = sorted({item["doc_type"] for item in documents})
    selected_types = st.multiselect(
        "Document types",
        options=available_types,
        default=available_types,
    )
    filtered_documents = [
        item
        for item in documents
        if item["doc_type"] in selected_types
        and _document_matches_search(item, search_term)
    ]
    if not filtered_documents:
        st.warning("No documents match the current filters.")
        return

    metric_a, metric_b, metric_c = st.columns(3)
    metric_a.metric("Filtered Docs", len(filtered_documents))
    metric_b.metric("Filtered Chunks", sum(item["chunk_count"] for item in filtered_documents))
    metric_c.metric("Doc Types", len({item["doc_type"] for item in filtered_documents}))

    st.dataframe(filtered_documents, use_container_width=True)

    selected_document_id = st.selectbox(
        "Select document",
        options=[item["id"] for item in filtered_documents],
        format_func=lambda doc_id: next(
            (
                f'{item["filename"]} ({item["chunk_count"]} chunks)'
                for item in filtered_documents
                if item["id"] == doc_id
            ),
            doc_id,
        ),
    )

    if not selected_document_id:
        return

    detail = service.get_document_detail(selected_document_id)
    overview = service.get_document_overview(selected_document_id)
    st.subheader("Document Detail")
    metric_x, metric_y, metric_z, metric_w = st.columns(4)
    metric_x.metric("Chunks", overview["chunk_count"])
    metric_y.metric("Words", overview["word_count"])
    metric_z.metric("Source Size", overview["source_size_bytes"])
    metric_w.metric("Avg Chunk Len", overview["average_chunk_length"])

    metric_m, metric_n = st.columns(2)
    metric_m.metric("Image Assets", overview.get("image_asset_count", 0))
    metric_n.metric("Multimodal", overview.get("multimodal_status") or "n/a")

    st.json(
        {
            "document_id": detail["document_id"],
            "filename": detail["filename"],
            "source_path": detail["source_path"],
            "doc_type": detail["doc_type"],
            "content_length": detail["content_length"],
            "chunk_count": detail["chunk_count"],
            "metadata": detail["metadata"],
            "assets": detail["assets"],
        },
        expanded=True,
    )

    st.subheader("Metadata")
    st.dataframe(metadata_rows(detail["metadata"]), use_container_width=True)

    st.subheader("Assets")
    if detail["assets"]:
        st.dataframe(detail["assets"], use_container_width=True)
    else:
        st.info("No multimodal assets recorded for this document yet.")

    st.subheader("Chunk Summary")
    st.dataframe(
        [
            {
                "chunk_index": chunk["chunk_index"],
                "start_offset": chunk["start_offset"],
                "end_offset": chunk["end_offset"],
                "length": len(chunk["text"]),
                "preview": chunk["text"][:120],
            }
            for chunk in detail["chunks"]
        ],
        use_container_width=True,
    )

    st.subheader("Chunks")
    for chunk in detail["chunks"]:
        with st.expander(
            f'Chunk {chunk["chunk_index"]} [{chunk["start_offset"]}, {chunk["end_offset"]}]'
        ):
            st.code(chunk["text"], language="markdown")


def render_ingestion_page() -> None:
    """Render the ingestion and collection maintenance page."""
    service = DashboardService()
    st.title("Ingestion Manager")

    with st.form("ingest_form"):
        source_path = st.text_input("Local file path", placeholder="D:\\docs\\sample.md")
        submit_ingest = st.form_submit_button("Ingest document")

    if submit_ingest:
        normalized_path = source_path.strip()
        if not normalized_path:
            st.error("A local file path is required.")
        elif not Path(normalized_path).exists():
            st.error("The provided file path does not exist.")
        else:
            try:
                result = service.ingest_document(normalized_path)
            except Exception as exc:
                st.error(str(exc))
            else:
                st.success(
                    f'Ingested document {result["document_id"]} with {result["chunk_count"]} chunks.'
                )
                st.caption(f'Trace ID: {result["trace_id"]}')

    st.subheader("Collection Maintenance")
    collections = service.list_collections()
    collection_name = collections[0]["name"] if collections else None

    if st.button("Rebuild active collection", type="secondary", disabled=collection_name is None):
        try:
            result = service.rebuild_collection(collection_name)
        except NotFoundError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success(
                "Rebuild completed: "
                f'{result["rebuilt_document_count"]}/{result["requested_document_count"]} documents rebuilt.'
            )
            if result["failures"]:
                st.warning(result["failures"])

    st.subheader("Delete Document")
    documents = service.list_documents()
    if not documents:
        st.info("No documents available for deletion.")
        return

    document_id = st.selectbox(
        "Select document to delete",
        options=[item["id"] for item in documents],
        format_func=lambda doc_id: next(
            (
                f'{item["filename"]} ({item["chunk_count"]} chunks)'
                for item in documents
                if item["id"] == doc_id
            ),
            doc_id,
        ),
        key="delete_document_id",
    )
    if st.button("Delete selected document", type="primary"):
        try:
            result = service.delete_document(document_id)
        except NotFoundError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success(
                f'Deleted document {result["document_id"]} and removed {result["deleted_chunk_count"]} chunks.'
            )


def render_traces_page() -> None:
    """Render the trace diagnostics page."""
    service = DashboardService()

    st.title("Trace Diagnostics")
    limit = st.slider("Recent traces", min_value=5, max_value=100, value=20, step=5)
    view_mapping = {
        "All": None,
        "Ingestion": "ingestion",
        "Query": "query",
        "Answers": "answer_generation",
        "Evaluations": "evaluation",
    }
    if st.session_state.get("dashboard_trace_view") not in view_mapping:
        st.session_state["dashboard_trace_view"] = "All"
    selected_view = st.radio(
        "Trace view",
        options=list(view_mapping.keys()),
        horizontal=True,
        key="dashboard_trace_view",
    )
    key_prefix = selected_view.lower().replace(" ", "_")
    _render_trace_tab(
        service,
        trace_type=view_mapping[selected_view],
        limit=limit,
        key_prefix=key_prefix,
    )


def render_answers_page() -> None:
    """Render grounded answer generation page."""
    service = DashboardService()
    st.title("Answers")

    default_top_k = int(service.get_settings().get("retrieval", {}).get("top_k", 5))
    with st.form("answer_generation_form"):
        query = st.text_area(
            "Question",
            placeholder="Ask a grounded question against the current knowledge base",
        )
        top_k = st.number_input("Top K", min_value=1, max_value=20, value=default_top_k, step=1)
        submit = st.form_submit_button("Generate grounded answer")

    if submit:
        normalized_query = query.strip()
        if not normalized_query:
            st.error("A question is required.")
        else:
            try:
                response = service.generate_answer(normalized_query, top_k=int(top_k))
            except Exception as exc:
                st.error(str(exc))
            else:
                st.session_state["dashboard_last_answer_response"] = response

    response = st.session_state.get("dashboard_last_answer_response")
    if not response:
        st.info("Run an answer generation request to inspect retrieval and generation diagnostics.")
        return

    trace_summary = service.get_trace_detail_summary(response["trace_id"])
    navigation = service.get_trace_navigation_context(response["trace_id"])
    linked_query = navigation.get("linked_query")

    st.subheader("Answer")
    st.write(response["answer"])

    metric_a, metric_b, metric_c, metric_d = st.columns(4)
    metric_a.metric("Answer Trace", response["trace_id"][:8])
    metric_b.metric("Query Trace", (trace_summary.get("query_trace_id") or "n/a")[:8])
    metric_c.metric("LLM Path", "LLM" if response["generated_by_llm"] else "Fallback")
    metric_d.metric("Sources", len(response["sources"]))

    metric_e, metric_f, metric_g = st.columns(3)
    metric_e.metric("Provider", trace_summary.get("provider_label") or "n/a")
    metric_f.metric("Prompt", trace_summary.get("prompt_label") or "n/a")
    metric_g.metric("Rerank", "On" if trace_summary.get("rerank_applied") else "Off")

    if response.get("generation_error"):
        st.warning(response["generation_error"])

    nav_col_a, nav_col_b = st.columns(2)
    if nav_col_a.button("Open answer trace diagnostics", key="answer_trace_jump"):
        _navigate_to_trace(response["trace_id"], "answer_generation")
    if linked_query and nav_col_b.button("Open linked query trace", key="query_trace_jump"):
        _navigate_to_trace(linked_query["trace_id"], "query")

    st.subheader("Troubleshooting Snapshot")
    st.dataframe(
        _detail_rows(
            {
                "query": trace_summary.get("query"),
                "query_trace_id": trace_summary.get("query_trace_id"),
                "provider": trace_summary.get("provider_label"),
                "prompt": trace_summary.get("prompt_label"),
                "generated_by_llm": trace_summary.get("generated_by_llm"),
                "fallback_used": trace_summary.get("fallback_used"),
                "source_count": trace_summary.get("source_count"),
                "error_message": trace_summary.get("error_message"),
            }
        ),
        use_container_width=True,
    )

    st.subheader("Execution Chain")
    chain_rows = [
        {
            "role": "answer",
            "trace_id": response["trace_id"],
            "trace_type": "answer_generation",
            "status": "fallback" if trace_summary.get("fallback_used") else "ok",
            "provider": trace_summary.get("provider_label"),
            "prompt": trace_summary.get("prompt_label"),
        }
    ]
    if linked_query:
        chain_rows.append(
            {
                "role": "query",
                "trace_id": linked_query["trace_id"],
                "trace_type": linked_query["trace_type"],
                "status": linked_query["status"],
                "provider": linked_query.get("provider_label"),
                "prompt": linked_query.get("prompt_label"),
            }
        )
    st.dataframe(chain_rows, use_container_width=True)

    st.subheader("Sources")
    st.dataframe(response["sources"], use_container_width=True)

    st.subheader("Retrieved Results")
    st.dataframe(response["results"], use_container_width=True)


def render_evaluations_page() -> None:
    """Render the evaluation page."""
    service = DashboardService()
    st.title("Evaluations")

    settings = service.get_settings()
    default_dataset_path = settings.get("evaluation", {}).get("default_test_set_path", "")
    default_top_k = settings.get("evaluation", {}).get("top_k", 5)

    with st.form("evaluation_form"):
        dataset_path = st.text_input("Dataset path", value=default_dataset_path)
        top_k = st.number_input("Top K", min_value=1, max_value=20, value=int(default_top_k), step=1)
        submit = st.form_submit_button("Run evaluation")

    if submit:
        try:
            result = service.run_evaluation(dataset_path=dataset_path.strip() or None, top_k=int(top_k))
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success(
                "Evaluation completed: "
                f'hit_rate={result["summary"]["hit_rate"]}, mrr={result["summary"]["mrr"]}'
            )
            st.caption(f'Report ID: {result["report_id"]}')
            st.caption(f'Trace ID: {result["trace_id"]}')

    reports = service.list_evaluation_reports(limit=20)
    if not reports:
        st.info("No evaluation reports available yet.")
        return

    st.subheader("Recent Reports")
    st.dataframe(reports, use_container_width=True)

    selected_report_id = st.selectbox(
        "Select report",
        options=[item["report_id"] for item in reports],
    )
    if not selected_report_id:
        return

    detail = service.get_evaluation_report_detail(selected_report_id)
    st.subheader("Summary")
    metric_a, metric_b, metric_c, metric_d = st.columns(4)
    metric_a.metric("Total Cases", detail["summary"]["total_cases"])
    metric_b.metric("Hit Rate", detail["summary"]["hit_rate"])
    metric_c.metric("MRR", detail["summary"]["mrr"])
    metric_d.metric("Failed Cases", detail["summary"]["failed_case_count"])
    st.json(
        {
            "report_id": detail["report_id"],
            "dataset_path": detail["dataset_path"],
            "started_at": detail["started_at"],
            "finished_at": detail["finished_at"],
            "summary": detail["summary"],
            "trace_id": detail["trace_id"],
        },
        expanded=True,
    )

    st.subheader("Case Results")
    show_failed_only = st.checkbox("Show failed cases only", value=False)
    case_search = st.text_input("Search case id or query", key="evaluation_case_search")
    cases = detail["cases"]
    if show_failed_only:
        cases = [item for item in cases if not item["hit"]]
    if case_search.strip():
        needle = case_search.strip().lower()
        cases = [
            item
            for item in cases
            if needle in item["case_id"].lower() or needle in item["query"].lower()
        ]
    st.dataframe(cases, use_container_width=True)


def _render_trace_tab(
    service: DashboardService,
    *,
    trace_type: str | None,
    limit: int,
    key_prefix: str,
) -> None:
    """Render a single trace diagnostics view."""
    traces = service.list_trace_overview(trace_type=trace_type, limit=limit)
    if not traces:
        st.info("No traces available yet.")
        return

    statuses = sorted({item["status"] for item in traces})
    selected_statuses = st.multiselect(
        "Statuses",
        options=statuses,
        default=statuses,
        key=f"{key_prefix}_statuses",
    )
    search_term = st.text_input(
        "Search trace metadata",
        placeholder="query, provider, prompt, path, dataset, trace id",
        key=f"{key_prefix}_search",
    )
    filtered = [
        item
        for item in traces
        if item["status"] in selected_statuses and _trace_matches_search(item, search_term)
    ]
    if not filtered:
        st.warning("No traces match the current filters.")
        return

    summary = service.get_trace_summary(trace_type=trace_type, limit=limit)
    filtered_summary = _build_filtered_trace_summary(filtered)

    metric_a, metric_b, metric_c, metric_d = st.columns(4)
    metric_a.metric("Filtered", len(filtered))
    metric_b.metric("Errors", filtered_summary["error_count"])
    metric_c.metric(
        "Fallback/Skipped",
        filtered_summary["fallback_count"] + filtered_summary["skipped_count"],
    )
    metric_d.metric("Avg Elapsed ms", filtered_summary["average_elapsed_ms"])

    detail_a, detail_b, detail_c, detail_d, detail_e = st.columns(5)
    detail_a.metric("Created", filtered_summary["created_count"])
    detail_b.metric("Replaced", filtered_summary["replaced_count"])
    detail_c.metric("Skipped", filtered_summary["skipped_count"])
    detail_d.metric("Fallback", filtered_summary["fallback_count"])
    detail_e.metric("OK", filtered_summary["ok_count"])

    st.subheader("Status Summary")
    st.dataframe(
        [
            {"status": status_name, "count": count}
            for status_name, count in filtered_summary["status_counts"].items()
        ],
        use_container_width=True,
    )

    st.caption(
        "Loaded summary: "
        f'{summary["total_traces"]} traces across {", ".join(f"{k}={v}" for k, v in summary["trace_type_counts"].items()) or "no trace types"}.'
    )

    st.subheader("Failure Hotspots")
    _render_failure_hotspots(filtered, key_prefix=key_prefix)

    failure_samples = build_failure_sample_rows(filtered)
    st.subheader("Failure Samples")
    if failure_samples:
        st.dataframe(failure_samples, use_container_width=True)
    else:
        st.info("No failure or fallback samples in the current selection.")

    st.subheader("Operational Queue")
    st.dataframe(
        [
            {
                "trace_type": item["trace_type"],
                "status": item["status"],
                "started_at": item["started_at"],
                "elapsed_ms": item["total_elapsed_ms"],
                "query": item["query"],
                "provider": item.get("provider_label"),
                "prompt": item.get("prompt_label"),
                "query_trace_id": item.get("query_trace_id"),
                "error_message": item.get("error_message"),
            }
            for item in filtered
        ],
        use_container_width=True,
    )

    _apply_focus_trace(filtered, key_prefix=key_prefix)
    selected_trace_id = st.selectbox(
        "Select trace",
        options=[item["trace_id"] for item in filtered],
        format_func=lambda trace_id: next(
            (
                f'{item["trace_type"]} | {item["status"]} | {item["trace_id"][:8]}'
                for item in filtered
                if item["trace_id"] == trace_id
            ),
            trace_id,
        ),
        key=f"{key_prefix}_trace_id",
    )
    if not selected_trace_id:
        return

    selected_overview = next(item for item in filtered if item["trace_id"] == selected_trace_id)
    try:
        detail = service.get_trace_detail(selected_trace_id)
    except NotFoundError as exc:
        st.error(str(exc))
        return

    detail_summary = service.get_trace_detail_summary(selected_trace_id)
    navigation = service.get_trace_navigation_context(selected_trace_id)
    linked_query = navigation.get("linked_query")
    related_answers = navigation.get("related_answers", [])
    stage_rows = build_stage_timing_rows(detail["stages"])

    st.subheader("Execution Chain")
    if selected_overview["trace_type"] == "answer_generation":
        if linked_query:
            st.dataframe(
                [
                    {
                        "role": "linked_query",
                        "trace_id": linked_query["trace_id"],
                        "status": linked_query["status"],
                        "provider": linked_query.get("provider_label"),
                        "elapsed_ms": linked_query["total_elapsed_ms"],
                        "query": linked_query.get("query"),
                    }
                ],
                use_container_width=True,
            )
            if st.button("Open linked query trace", key=f"{key_prefix}_open_linked_query"):
                _navigate_to_trace(linked_query["trace_id"], "query")
        else:
            st.info("No linked query trace recorded for this answer trace.")
    elif selected_overview["trace_type"] == "query":
        if related_answers:
            st.dataframe(
                [
                    {
                        "trace_id": item["trace_id"],
                        "status": item["status"],
                        "provider": item.get("provider_label"),
                        "prompt": item.get("prompt_label"),
                        "elapsed_ms": item["total_elapsed_ms"],
                        "query": item.get("query"),
                    }
                    for item in related_answers
                ],
                use_container_width=True,
            )
            selected_related_answer = st.selectbox(
                "Related answer traces",
                options=[item["trace_id"] for item in related_answers],
                format_func=lambda trace_id: next(
                    (
                        f'{item["status"]} | {item["trace_id"][:8]} | {item.get("provider_label") or "n/a"}'
                        for item in related_answers
                        if item["trace_id"] == trace_id
                    ),
                    trace_id,
                ),
                key=f"{key_prefix}_related_answer_trace_id",
            )
            if st.button("Open selected answer trace", key=f"{key_prefix}_open_related_answer"):
                _navigate_to_trace(selected_related_answer, "answer_generation")
        else:
            st.info("No answer traces currently reference this query trace.")
    elif related_answers:
        st.dataframe(related_answers, use_container_width=True)

    st.subheader("Troubleshooting Snapshot")
    summary_metric_a, summary_metric_b, summary_metric_c, summary_metric_d = st.columns(4)
    summary_metric_a.metric("Status", selected_overview["status"])
    summary_metric_b.metric("Elapsed ms", selected_overview["total_elapsed_ms"])
    summary_metric_c.metric("Provider", selected_overview.get("provider_label") or "n/a")
    summary_metric_d.metric("Prompt", selected_overview.get("prompt_label") or "n/a")

    summary_metric_e, summary_metric_f, summary_metric_g, summary_metric_h = st.columns(4)
    summary_metric_e.metric("Last Stage", selected_overview.get("last_stage") or "n/a")
    summary_metric_f.metric("Sources", detail_summary.get("source_count") or 0)
    summary_metric_g.metric("Rerank", "On" if detail_summary.get("rerank_applied") else "Off")
    summary_metric_h.metric("Linked Answers", len(related_answers))

    if detail_summary.get("error_message"):
        st.error(detail_summary["error_message"])
    elif detail_summary.get("fallback_used"):
        st.warning("This trace completed via fallback path.")

    st.dataframe(
        _detail_rows(
            {
                "trace_type": detail_summary.get("trace_type"),
                "query": detail_summary.get("query"),
                "top_k": detail_summary.get("top_k"),
                "query_trace_id": detail_summary.get("query_trace_id"),
                "collection_name": detail_summary.get("collection_name"),
                "source_path": detail_summary.get("source_path"),
                "dataset_path": detail_summary.get("dataset_path"),
                "document_id": detail_summary.get("document_id"),
                "provider": detail_summary.get("provider_label"),
                "embedding_provider": detail_summary.get("embedding_provider"),
                "rerank_provider": detail_summary.get("rerank_provider"),
                "prompt": detail_summary.get("prompt_label"),
                "system_prompt_length": detail_summary.get("system_prompt_length"),
                "user_prompt_length": detail_summary.get("user_prompt_length"),
                "dense_result_count": detail_summary.get("dense_result_count"),
                "sparse_result_count": detail_summary.get("sparse_result_count"),
                "fusion_result_count": detail_summary.get("fusion_result_count"),
                "rerank_result_count": detail_summary.get("rerank_result_count"),
                "evaluation_case_count": detail_summary.get("evaluation_case_count"),
            }
        ),
        use_container_width=True,
    )

    st.subheader("Slowest Stages")
    st.dataframe(
        [
            {
                "name": row["name"],
                "elapsed_ms": row["elapsed_ms"],
                "cumulative_ms": row["cumulative_ms"],
                "has_error": row["has_error"],
            }
            for row in sorted(stage_rows, key=lambda row: row["elapsed_ms"], reverse=True)[:5]
        ],
        use_container_width=True,
    )

    st.subheader("Stage Timing")
    st.dataframe(
        [
            {
                "name": row["name"],
                "elapsed_ms": row["elapsed_ms"],
                "cumulative_ms": row["cumulative_ms"],
                "timestamp": row["timestamp"],
                "has_error": row["has_error"],
            }
            for row in stage_rows
        ],
        use_container_width=True,
    )

    st.subheader("Stage Payload Drill-down")
    for row in stage_rows:
        with st.expander(f'{row["name"]} ({row["elapsed_ms"]} ms)'):
            st.json(row["data"], expanded=True)

    with st.expander("Raw Trace Payload"):
        st.json(
            {
                "trace_id": detail["trace_id"],
                "trace_type": detail["trace_type"],
                "started_at": detail["started_at"],
                "finished_at": detail["finished_at"],
                "total_elapsed_ms": detail["total_elapsed_ms"],
                "metadata": detail["metadata"],
            },
            expanded=True,
        )


def _document_matches_search(document: dict, search_term: str) -> bool:
    """Return whether a document row matches the search filter."""
    if not search_term.strip():
        return True
    needle = search_term.strip().lower()
    return needle in document["filename"].lower() or needle in document["source_path"].lower()


def _trace_matches_search(trace: dict, search_term: str) -> bool:
    """Return whether a trace overview row matches the search filter."""
    if not search_term.strip():
        return True
    needle = search_term.strip().lower()
    haystacks = [
        str(trace.get("query") or "").lower(),
        str(trace.get("provider_label") or "").lower(),
        str(trace.get("prompt_label") or "").lower(),
        str(trace.get("source_path") or "").lower(),
        str(trace.get("dataset_path") or "").lower(),
        str(trace.get("document_id") or "").lower(),
        str(trace.get("trace_id") or "").lower(),
        str(trace.get("error_message") or "").lower(),
    ]
    return any(needle in haystack for haystack in haystacks)


def _build_filtered_trace_summary(filtered: list[dict]) -> dict:
    """Compute summary metrics for the currently filtered trace rows."""
    total = len(filtered)
    average_elapsed_ms = (
        round(sum(float(item.get("total_elapsed_ms", 0.0)) for item in filtered) / total, 2)
        if total
        else 0.0
    )
    status_counts: dict[str, int] = {}
    for item in filtered:
        status = str(item.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "average_elapsed_ms": average_elapsed_ms,
        "status_counts": dict(sorted(status_counts.items())),
        "error_count": status_counts.get("error", 0),
        "fallback_count": status_counts.get("fallback", 0),
        "skipped_count": status_counts.get("skipped", 0),
        "replaced_count": status_counts.get("replaced", 0),
        "created_count": status_counts.get("created", 0),
        "ok_count": status_counts.get("ok", 0),
    }


def _render_failure_hotspots(trace_rows: list[dict], *, key_prefix: str) -> None:
    """Render grouped failure/fallback aggregates for the current trace selection."""
    failure_rows = build_failure_sample_rows(trace_rows)
    if not failure_rows:
        st.info("No failure or fallback traces in the current selection.")
        return

    group_by = st.radio(
        "Group failure samples by",
        options=["query", "provider", "prompt"],
        horizontal=True,
        key=f"{key_prefix}_failure_group",
    )
    grouped = build_failure_hotspot_rows(trace_rows, group_by=group_by)
    label_column = {
        "query": "query",
        "provider": "provider",
        "prompt": "prompt",
    }[group_by]
    st.dataframe(
        [
            {
                label_column: row["label"],
                "trace_count": row["trace_count"],
                "errors": row["error_count"],
                "fallbacks": row["fallback_count"],
                "avg_elapsed_ms": row["average_elapsed_ms"],
                "max_elapsed_ms": row["max_elapsed_ms"],
                "providers": row["providers"],
                "prompts": row["prompts"],
                "sample_error": row["sample_error"],
                "latest_trace_id": row["latest_trace_id"],
            }
            for row in grouped
        ],
        use_container_width=True,
    )


def _navigate_to_trace(trace_id: str, trace_type: str | None) -> None:
    """Jump to the traces page and focus a specific trace."""
    st.session_state["dashboard_selected_page"] = "Traces"
    st.session_state["dashboard_trace_view"] = _resolve_trace_view_name(trace_type)
    st.session_state["dashboard_focus_trace_id"] = trace_id
    st.rerun()


def _resolve_trace_view_name(trace_type: str | None) -> str:
    """Map a trace type to the diagnostics view label."""
    mapping = {
        None: "All",
        "ingestion": "Ingestion",
        "query": "Query",
        "answer_generation": "Answers",
        "evaluation": "Evaluations",
    }
    return mapping.get(trace_type, "All")


def _apply_focus_trace(filtered: list[dict], *, key_prefix: str) -> None:
    """Apply deferred trace focus from cross-page navigation."""
    focus_trace_id = st.session_state.get("dashboard_focus_trace_id")
    selection_key = f"{key_prefix}_trace_id"
    if focus_trace_id and any(item["trace_id"] == focus_trace_id for item in filtered):
        st.session_state[selection_key] = focus_trace_id
        st.session_state.pop("dashboard_focus_trace_id", None)
    elif selection_key not in st.session_state and filtered:
        st.session_state[selection_key] = filtered[0]["trace_id"]


def _detail_rows(payload: dict) -> list[dict]:
    """Flatten a detail payload into table rows, omitting empty values."""
    return [
        {"field": key, "value": value}
        for key, value in payload.items()
        if value not in (None, "", [], {})
    ]
