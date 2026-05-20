"""Service facades for the local dashboard."""

from __future__ import annotations

from rag_mcp.application.dto.models import EvaluationRunRequest
from rag_mcp.application.dto.models import GenerateAnswerRequest
from rag_mcp.application.dto.models import IngestRequest
from rag_mcp.core.container import get_container
from rag_mcp.core.exceptions import NotFoundError
from rag_mcp.core.settings import settings_to_dict
from rag_mcp.observability.dashboard.view_models import (
    build_document_overview,
    build_trace_detail_summary,
    build_trace_overview,
    build_trace_summary,
)


class DashboardService:
    """Thin facade over application use cases for dashboard consumers."""

    def __init__(self) -> None:
        self.container = get_container()

    def get_settings(self) -> dict:
        """Return the current application settings as plain data."""
        return settings_to_dict(self.container.settings)

    def get_status(self) -> dict:
        """Return aggregate knowledge-base status."""
        return self.container.knowledge_status_use_case.execute().model_dump()

    def list_collections(self) -> list[dict]:
        """Return configured collection summaries."""
        return [item.model_dump() for item in self.container.list_collections_use_case.execute()]

    def list_documents(self) -> list[dict]:
        """Return document list items."""
        return [item.model_dump(mode="json") for item in self.container.list_documents_use_case.execute()]

    def get_document_detail(self, document_id: str) -> dict:
        """Return a document detail payload."""
        return self.container.get_document_detail_use_case.execute(document_id).model_dump(mode="json")

    def get_document_overview(self, document_id: str) -> dict:
        """Return a dashboard-friendly document overview."""
        return build_document_overview(self.get_document_detail(document_id))

    def ingest_document(self, path: str) -> dict:
        """Ingest a document from a local filesystem path."""
        return self.container.ingest_use_case.execute(IngestRequest(path=path)).model_dump()

    def delete_document(self, document_id: str) -> dict:
        """Delete a document and its indexes."""
        return self.container.delete_document_use_case.execute(document_id).model_dump()

    def rebuild_collection(self, collection_name: str | None = None) -> dict:
        """Rebuild the active collection."""
        return self.container.rebuild_collection_use_case.execute(collection_name).model_dump()

    def list_traces(self, trace_type: str | None = None, limit: int = 20) -> list[dict]:
        """Return trace list items."""
        return [
            item.model_dump(mode="json")
            for item in self.container.list_traces_use_case.execute(trace_type=trace_type, limit=limit)
        ]

    def get_trace_detail(self, trace_id: str) -> dict:
        """Return a trace detail payload."""
        return self.container.get_trace_detail_use_case.execute(trace_id).model_dump(mode="json")

    def list_trace_overview(self, trace_type: str | None = None, limit: int = 20) -> list[dict]:
        """Return enriched trace overview rows for dashboard display."""
        traces = self.container.trace_repository.list_traces(trace_type=trace_type, limit=limit)
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
            for item in self.container.trace_repository.list_traces(limit=None)
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
        """Run an evaluation report."""
        return self.container.run_evaluation_use_case.execute(
            EvaluationRunRequest(dataset_path=dataset_path, top_k=top_k)
        ).model_dump()

    def list_evaluation_reports(self, limit: int = 20) -> list[dict]:
        """Return recent evaluation reports."""
        return [
            item.model_dump()
            for item in self.container.list_evaluation_reports_use_case.execute(limit=limit)
        ]

    def get_evaluation_report_detail(self, report_id: str) -> dict:
        """Return a single evaluation report detail payload."""
        return self.container.get_evaluation_report_detail_use_case.execute(report_id).model_dump()

    def generate_answer(self, query: str, top_k: int = 5) -> dict:
        """Generate a grounded answer from the active knowledge base."""
        return self.container.generate_answer_use_case.execute(
            GenerateAnswerRequest(query=query, top_k=top_k)
        ).model_dump()
