"""Service facades for the local dashboard."""

from __future__ import annotations

from rag_mcp.application.handlers import (
    generate_answer, get_document_detail, get_knowledge_status, ingest_document,
    list_documents, list_traces, rebuild_collection, delete_document,
    run_evaluation, list_evaluation_reports, get_evaluation_report_detail,
    list_collections, get_trace_detail,
)
from rag_mcp.core.exceptions import NotFoundError
from rag_mcp.core.settings import settings_to_dict
from rag_mcp.factory import get_rag
from rag_mcp.observability.dashboard.view_models import (
    build_document_overview,
    build_trace_detail_summary,
    build_trace_overview,
    build_trace_summary,
)


class DashboardService:
    """Thin facade over RAG system for dashboard consumers."""

    def __init__(self) -> None:
        self.rag = get_rag()

    def get_settings(self) -> dict:
        return settings_to_dict(self.rag.settings)

    def get_status(self) -> dict:
        return get_knowledge_status(self.rag)

    def list_collections(self) -> list[dict]:
        return list_collections(self.rag)

    def list_documents(self) -> list[dict]:
        return list_documents(self.rag)

    def get_document_detail(self, document_id: str) -> dict:
        return get_document_detail(self.rag, document_id)

    def get_document_overview(self, document_id: str) -> dict:
        return build_document_overview(self.get_document_detail(document_id))

    def ingest_document(self, path: str) -> dict:
        return ingest_document(self.rag, path)

    def delete_document(self, document_id: str) -> dict:
        return delete_document(self.rag, document_id)

    def rebuild_collection(self, collection_name: str | None = None) -> dict:
        return rebuild_collection(self.rag, collection_name)

    def list_traces(self, trace_type: str | None = None, limit: int = 20) -> list[dict]:
        return list_traces(self.rag, trace_type, limit)

    def get_trace_detail(self, trace_id: str) -> dict:
        return get_trace_detail(self.rag, trace_id)

    def list_trace_overview(self, trace_type: str | None = None, limit: int = 20) -> list[dict]:
        traces = self.rag.trace_repository.list_traces(trace_type=trace_type, limit=limit)
        return [build_trace_overview(item) for item in traces]

    def get_trace_summary(self, trace_type: str | None = None, limit: int = 20) -> dict:
        """Return aggregate operational metrics for trace explorer pages."""
        return build_trace_summary(self.list_trace_overview(trace_type=trace_type, limit=limit))

    def get_trace_detail_summary(self, trace_id: str) -> dict:
        """Return concise operational highlights for a single trace."""
        return build_trace_detail_summary(self.get_trace_detail(trace_id))

    def get_trace_navigation_context(self, trace_id: str, related_limit: int = 20) -> dict:
        """Return linked query/answer traces for troubleshooting navigation."""
        selected_detail = self.get_trace_detail(trace_id)
        selected = build_trace_overview(selected_detail)
        all_traces = [
            build_trace_overview(item)
            for item in self.rag.trace_repository.list_traces(limit=None)
        ]

        selected_query_trace_id = selected.get("query_trace_id")
        linked_query = None
        if selected_query_trace_id:
            linked_query = next(
                (item for item in all_traces if item.get("trace_id") == selected_query_trace_id),
                None,
            )

        related_answers = [
            item
            for item in all_traces
            if item.get("trace_type") == "answer_generation"
            and (
                item.get("query_trace_id") == trace_id
                or (
                    selected_query_trace_id is not None
                    and item.get("query_trace_id") == selected_query_trace_id
                )
            )
            and item.get("trace_id") != trace_id
        ]
        related_answers.sort(
            key=lambda item: (item.get("started_at") or "", item.get("trace_id") or ""),
            reverse=True,
        )
        return {
            "selected": selected,
            "linked_query": linked_query,
            "related_answers": related_answers[:related_limit],
        }

    def run_evaluation(self, dataset_path: str | None = None, top_k: int | None = None) -> dict:
        return run_evaluation(self.rag, dataset_path, top_k)

    def list_evaluation_reports(self, limit: int = 20) -> list[dict]:
        return list_evaluation_reports(self.rag, limit)

    def get_evaluation_report_detail(self, report_id: str) -> dict:
        return get_evaluation_report_detail(self.rag, report_id)

    def generate_answer(self, query: str, top_k: int = 5) -> dict:
        """Generate a grounded answer from the active knowledge base."""
        return generate_answer(self.rag, query, top_k)
