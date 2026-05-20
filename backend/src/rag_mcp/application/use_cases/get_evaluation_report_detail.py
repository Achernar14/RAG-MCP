"""Evaluation report detail use case."""

from __future__ import annotations

from rag_mcp.application.dto.models import (
    EvaluationCaseResultResponse,
    EvaluationReportDetailResponse,
    EvaluationSummaryResponse,
)
from rag_mcp.core.exceptions import NotFoundError


class GetEvaluationReportDetailUseCase:
    """Return a single persisted evaluation report."""

    def __init__(self, evaluation_report_repository) -> None:
        self.evaluation_report_repository = evaluation_report_repository

    def execute(self, report_id: str) -> EvaluationReportDetailResponse:
        """Return report detail by id."""
        report = self.evaluation_report_repository.get(report_id)
        if report is None:
            raise NotFoundError(f"Evaluation report not found: {report_id}")

        return EvaluationReportDetailResponse(
            report_id=report.report_id,
            dataset_path=report.dataset_path,
            started_at=report.started_at.isoformat(),
            finished_at=report.finished_at.isoformat() if report.finished_at else None,
            summary=EvaluationSummaryResponse(
                total_cases=report.summary.total_cases,
                hit_rate=report.summary.hit_rate,
                mrr=report.summary.mrr,
                top_k=report.summary.top_k,
                passed_case_count=report.summary.passed_case_count,
                failed_case_count=report.summary.failed_case_count,
            ),
            cases=[
                EvaluationCaseResultResponse(
                    case_id=item.case_id,
                    query=item.query,
                    retrieved_chunk_ids=item.retrieved_chunk_ids,
                    matched_chunk_ids=item.matched_chunk_ids,
                    hit=item.hit,
                    reciprocal_rank=item.reciprocal_rank,
                    top_k=item.top_k,
                    trace_id=item.trace_id,
                    metadata=item.metadata,
                )
                for item in report.cases
            ],
            trace_id=report.trace_id,
        )
