"""List evaluation reports use case."""

from __future__ import annotations

from rag_mcp.application.dto.models import EvaluationReportListItemResponse


class ListEvaluationReportsUseCase:
    """Return recent evaluation report summaries."""

    def __init__(self, evaluation_report_repository) -> None:
        self.evaluation_report_repository = evaluation_report_repository

    def execute(self, limit: int = 20) -> list[EvaluationReportListItemResponse]:
        """List recent persisted reports."""
        reports = self.evaluation_report_repository.list_reports(limit=limit)
        return [
            EvaluationReportListItemResponse(
                report_id=item.report_id,
                dataset_path=item.dataset_path,
                started_at=item.started_at.isoformat(),
                finished_at=item.finished_at.isoformat() if item.finished_at else None,
                total_cases=item.summary.total_cases,
                hit_rate=item.summary.hit_rate,
                mrr=item.summary.mrr,
                top_k=item.summary.top_k,
                trace_id=item.trace_id,
            )
            for item in reports
        ]
