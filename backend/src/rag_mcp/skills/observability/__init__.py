"""Observability skill: trace collection, browsing, and diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rag_mcp.application.dto.models import (
    TraceDetailResponse,
    TraceListItemResponse,
)
from rag_mcp.core.skill_registry import SkillDescriptor, ToolDescriptor

if TYPE_CHECKING:
    from rag_mcp.core.container import ApplicationContainer
    from rag_mcp.core.settings import Settings


class ObservabilitySkill:
    """Handles trace browsing and diagnostics."""

    @classmethod
    def descriptor(cls) -> SkillDescriptor:
        return SkillDescriptor(
            name="observability",
            version="1.0.0",
            description="Trace collection, browsing, and dashboard diagnostics",
            enabled_by_default=True,
            dependencies=[],
        )

    @classmethod
    def register_tools(cls, container: ApplicationContainer) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name="list_traces",
                description="List persisted traces with optional trace-type filtering.",
                handler=cls._list_traces(container),
                return_type=list[TraceListItemResponse],
            ),
            ToolDescriptor(
                name="get_trace_detail",
                description="Get a single persisted trace by trace id.",
                handler=cls._get_trace_detail(container),
                return_type=TraceDetailResponse,
            ),
        ]

    @classmethod
    def wire_container(cls, container: ApplicationContainer, settings: Settings) -> None:
        from rag_mcp.application.use_cases.list_traces import ListTracesUseCase
        from rag_mcp.application.use_cases.get_trace_detail import GetTraceDetailUseCase

        container.list_traces_use_case = ListTracesUseCase(
            trace_repository=container.trace_repository,
        )
        container.get_trace_detail_use_case = GetTraceDetailUseCase(
            trace_repository=container.trace_repository,
        )

    @staticmethod
    def _list_traces(container: ApplicationContainer):
        def list_traces(trace_type: str | None = None, limit: int = 20):
            return container.list_traces_use_case.execute(trace_type=trace_type, limit=limit)

        return list_traces

    @staticmethod
    def _get_trace_detail(container: ApplicationContainer):
        def get_trace_detail(trace_id: str):
            return container.get_trace_detail_use_case.execute(trace_id)

        return get_trace_detail
