"""Trace listing use case."""

from __future__ import annotations

from rag_mcp.application.dto.models import TraceListItemResponse


class ListTracesUseCase:
    """Return persisted traces with lightweight filtering."""

    def __init__(self, trace_repository) -> None:
        self.trace_repository = trace_repository

    def execute(self, trace_type: str | None = None, limit: int = 20) -> list[TraceListItemResponse]:
        """List traces ordered from most recent to least recent."""
        normalized_limit = max(1, min(limit, 100))
        payload = self.trace_repository.list_traces(
            trace_type=trace_type,
            limit=normalized_limit,
        )
        return [
            TraceListItemResponse(
                trace_id=item["trace_id"],
                trace_type=item["trace_type"],
                started_at=item["started_at"],
                finished_at=item.get("finished_at"),
                total_elapsed_ms=float(item.get("total_elapsed_ms", 0.0)),
                metadata=item.get("metadata", {}),
            )
            for item in payload
        ]
