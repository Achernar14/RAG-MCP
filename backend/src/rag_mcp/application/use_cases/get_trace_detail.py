"""Trace detail use case."""

from __future__ import annotations

from rag_mcp.application.dto.models import TraceDetailResponse
from rag_mcp.application.dto.models import TraceStageResponse
from rag_mcp.core.exceptions import NotFoundError


class GetTraceDetailUseCase:
    """Return a single persisted trace with full stage detail."""

    def __init__(self, trace_repository) -> None:
        self.trace_repository = trace_repository

    def execute(self, trace_id: str) -> TraceDetailResponse:
        """Load a trace by id and map it to a detail DTO."""
        payload = self.trace_repository.get_trace(trace_id)
        if payload is None:
            raise NotFoundError(f"Trace not found: {trace_id}")

        return TraceDetailResponse(
            trace_id=payload["trace_id"],
            trace_type=payload["trace_type"],
            started_at=payload["started_at"],
            finished_at=payload.get("finished_at"),
            total_elapsed_ms=float(payload.get("total_elapsed_ms", 0.0)),
            metadata=payload.get("metadata", {}),
            stages=[
                TraceStageResponse(
                    name=stage["name"],
                    elapsed_ms=float(stage.get("elapsed_ms", 0.0)),
                    timestamp=stage["timestamp"],
                    data=stage.get("data", {}),
                )
                for stage in payload.get("stages", [])
            ],
        )
