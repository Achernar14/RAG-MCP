"""Evaluation skill: retrieval evaluation and report management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rag_mcp.application.dto.models import (
    EvaluationReportDetailResponse,
    EvaluationReportListItemResponse,
)
from rag_mcp.core.skill_registry import SkillDescriptor, ToolDescriptor

if TYPE_CHECKING:
    from rag_mcp.core.container import ApplicationContainer
    from rag_mcp.core.settings import Settings


class EvaluationSkill:
    """Handles retrieval evaluation and report browsing."""

    @classmethod
    def descriptor(cls) -> SkillDescriptor:
        return SkillDescriptor(
            name="evaluation",
            version="1.0.0",
            description="Retrieval evaluation, report persistence, and browsing",
            enabled_by_default=True,
            dependencies=["retrieval"],
        )

    @classmethod
    def register_tools(cls, container: ApplicationContainer) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name="run_evaluation",
                description="Run retrieval evaluation against the configured golden dataset.",
                handler=cls._run_evaluation(container),
                return_type=EvaluationReportDetailResponse,
            ),
            ToolDescriptor(
                name="list_evaluation_reports",
                description="List recent persisted evaluation reports.",
                handler=cls._list_evaluation_reports(container),
                return_type=list[EvaluationReportListItemResponse],
            ),
            ToolDescriptor(
                name="get_evaluation_report",
                description="Get a single evaluation report by report id.",
                handler=cls._get_evaluation_report(container),
                return_type=EvaluationReportDetailResponse,
            ),
        ]

    @classmethod
    def wire_container(cls, container: ApplicationContainer, settings: Settings) -> None:
        from rag_mcp.application.use_cases.run_evaluation import RunEvaluationUseCase
        from rag_mcp.application.use_cases.list_evaluation_reports import ListEvaluationReportsUseCase
        from rag_mcp.application.use_cases.get_evaluation_report_detail import (
            GetEvaluationReportDetailUseCase,
        )

        container.run_evaluation_use_case = RunEvaluationUseCase(
            settings=settings,
            query_use_case=container.query_use_case,
            evaluation_report_repository=container.evaluation_report_repository,
            trace_collector=container.trace_collector,
        )
        container.list_evaluation_reports_use_case = ListEvaluationReportsUseCase(
            evaluation_report_repository=container.evaluation_report_repository,
        )
        container.get_evaluation_report_detail_use_case = GetEvaluationReportDetailUseCase(
            evaluation_report_repository=container.evaluation_report_repository,
        )

    @staticmethod
    def _run_evaluation(container: ApplicationContainer):
        from rag_mcp.application.dto.models import EvaluationRunRequest

        def run_evaluation(dataset_path: str | None = None, top_k: int | None = None):
            return container.run_evaluation_use_case.execute(
                EvaluationRunRequest(dataset_path=dataset_path, top_k=top_k)
            )

        return run_evaluation

    @staticmethod
    def _list_evaluation_reports(container: ApplicationContainer):
        def list_evaluation_reports(limit: int = 20):
            return container.list_evaluation_reports_use_case.execute(limit=limit)

        return list_evaluation_reports

    @staticmethod
    def _get_evaluation_report(container: ApplicationContainer):
        def get_evaluation_report(report_id: str):
            return container.get_evaluation_report_detail_use_case.execute(report_id)

        return get_evaluation_report
