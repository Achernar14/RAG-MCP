"""Evaluation execution use case."""

from __future__ import annotations

from datetime import datetime

from rag_mcp.application.dto.models import (
    EvaluationCaseResultResponse,
    EvaluationReportDetailResponse,
    EvaluationRunRequest,
    EvaluationSummaryResponse,
    QueryRequest,
)
from rag_mcp.core.tracing import TraceContext
from rag_mcp.infrastructure.evaluation.dataset_loader import load_evaluation_cases
from rag_mcp.domain.entities.models import EvaluationCaseResult, EvaluationReport, EvaluationSummary


class RunEvaluationUseCase:
    """Run retrieval evaluation against a golden dataset."""

    def __init__(self, settings, query_use_case, evaluation_report_repository, trace_collector) -> None:
        self.settings = settings
        self.query_use_case = query_use_case
        self.evaluation_report_repository = evaluation_report_repository
        self.trace_collector = trace_collector

    def execute(self, request: EvaluationRunRequest) -> EvaluationReportDetailResponse:
        """Run the evaluation flow and persist a report if configured."""
        dataset_path = request.dataset_path or self.settings.evaluation.default_test_set_path
        top_k = request.top_k or self.settings.evaluation.top_k
        trace = TraceContext(
            trace_type="evaluation",
            metadata={"dataset_path": dataset_path, "top_k": top_k},
        )

        cases = load_evaluation_cases(dataset_path)
        trace.record_stage(
            "load_dataset",
            {"case_count": len(cases)},
            0.0,
        )

        results: list[EvaluationCaseResult] = []
        for case in cases:
            query_response = self.query_use_case.execute(
                QueryRequest(query=case.query, top_k=top_k)
            )
            matched_chunk_ids, reciprocal_rank = self._match_case(case, query_response.results)
            result = EvaluationCaseResult(
                case_id=case.case_id,
                query=case.query,
                retrieved_chunk_ids=[item.chunk_id for item in query_response.results],
                matched_chunk_ids=matched_chunk_ids,
                hit=bool(matched_chunk_ids),
                reciprocal_rank=reciprocal_rank,
                top_k=top_k,
                trace_id=query_response.trace_id,
                metadata=case.metadata,
            )
            results.append(result)
            trace.record_stage(
                "evaluate_case",
                {
                    "case_id": case.case_id,
                    "hit": result.hit,
                    "reciprocal_rank": result.reciprocal_rank,
                },
                0.0,
            )

        summary = self._build_summary(results, top_k)
        trace.record_stage(
            "aggregate_metrics",
            {
                "total_cases": summary.total_cases,
                "hit_rate": summary.hit_rate,
                "mrr": summary.mrr,
            },
            0.0,
        )

        report = EvaluationReport(
            dataset_path=str(dataset_path),
            summary=summary,
            cases=results,
            trace_id=trace.trace_id,
        )
        if self.settings.evaluation.persist_reports:
            trace.record_stage(
                "persist_report",
                {"report_id": report.report_id},
                0.0,
            )
            report.finished_at = datetime.now(report.started_at.tzinfo)
            self.evaluation_report_repository.save(report)
        else:
            report.finished_at = datetime.now(report.started_at.tzinfo)

        trace.finish()
        self.trace_collector.collect(trace)
        return self._to_detail_response(report)

    def _match_case(self, case, results) -> tuple[list[str], float]:
        matched_chunk_ids: list[str] = []
        reciprocal_rank = 0.0

        for rank, result in enumerate(results, start=1):
            if self._result_matches_case(case, result):
                matched_chunk_ids.append(result.chunk_id)
                if reciprocal_rank == 0.0:
                    reciprocal_rank = 1.0 / rank
        return matched_chunk_ids, reciprocal_rank

    def _result_matches_case(self, case, result) -> bool:
        if case.expected_chunk_ids:
            return result.chunk_id in case.expected_chunk_ids
        if case.expected_document_ids:
            document_id = result.chunk_id.split(":", 1)[0]
            return document_id in case.expected_document_ids
        if case.expected_source_paths:
            source_path = result.source_path.replace("\\", "/")
            return any(source_path.endswith(item.replace("\\", "/")) for item in case.expected_source_paths)
        return False

    def _build_summary(self, results: list[EvaluationCaseResult], top_k: int) -> EvaluationSummary:
        total_cases = len(results)
        passed_case_count = sum(1 for item in results if item.hit)
        failed_case_count = total_cases - passed_case_count
        hit_rate = (passed_case_count / total_cases) if total_cases else 0.0
        mrr = (
            sum(item.reciprocal_rank for item in results) / total_cases
            if total_cases
            else 0.0
        )
        return EvaluationSummary(
            total_cases=total_cases,
            hit_rate=round(hit_rate, 4),
            mrr=round(mrr, 4),
            top_k=top_k,
            passed_case_count=passed_case_count,
            failed_case_count=failed_case_count,
        )

    def _to_detail_response(self, report: EvaluationReport) -> EvaluationReportDetailResponse:
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
