"""JSONL-backed evaluation report repository."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from rag_mcp.domain.entities.models import (
    EvaluationCaseResult,
    EvaluationReport,
    EvaluationSummary,
)


class JsonlEvaluationReportRepository:
    """Persist evaluation reports in JSONL format."""

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, report: EvaluationReport) -> None:
        """Append a report to disk."""
        payload = self._to_dict(report)
        with self.file_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def list_reports(self, limit: int = 20) -> list[EvaluationReport]:
        """Return recent reports."""
        reports = self._load_all()
        reports.sort(
            key=lambda item: (item.finished_at or item.started_at, item.report_id),
            reverse=True,
        )
        return reports[:limit]

    def get(self, report_id: str) -> EvaluationReport | None:
        """Return a report by id if present."""
        for report in self._load_all():
            if report.report_id == report_id:
                return report
        return None

    def _load_all(self) -> list[EvaluationReport]:
        if not self.file_path.exists():
            return []

        reports: list[EvaluationReport] = []
        with self.file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                reports.append(self._from_dict(json.loads(raw)))
        return reports

    def _to_dict(self, report: EvaluationReport) -> dict:
        payload = asdict(report)
        payload["started_at"] = report.started_at.isoformat()
        payload["finished_at"] = report.finished_at.isoformat() if report.finished_at else None
        return payload

    def _from_dict(self, payload: dict) -> EvaluationReport:
        summary_payload = payload["summary"]
        case_payloads = payload["cases"]
        return EvaluationReport(
            report_id=payload["report_id"],
            dataset_path=payload["dataset_path"],
            started_at=datetime.fromisoformat(payload["started_at"]),
            finished_at=(
                datetime.fromisoformat(payload["finished_at"])
                if payload.get("finished_at")
                else None
            ),
            summary=EvaluationSummary(
                total_cases=summary_payload["total_cases"],
                hit_rate=summary_payload["hit_rate"],
                mrr=summary_payload["mrr"],
                top_k=summary_payload["top_k"],
                passed_case_count=summary_payload["passed_case_count"],
                failed_case_count=summary_payload["failed_case_count"],
            ),
            cases=[
                EvaluationCaseResult(
                    case_id=item["case_id"],
                    query=item["query"],
                    retrieved_chunk_ids=item["retrieved_chunk_ids"],
                    matched_chunk_ids=item["matched_chunk_ids"],
                    hit=item["hit"],
                    reciprocal_rank=item["reciprocal_rank"],
                    top_k=item["top_k"],
                    trace_id=item.get("trace_id"),
                    metadata=item.get("metadata", {}),
                )
                for item in case_payloads
            ],
            trace_id=payload.get("trace_id"),
        )
