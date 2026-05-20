"""Trace primitives for ingestion and query flows."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    """Return an ISO timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TraceStage:
    """A single timed trace stage."""

    name: str
    data: dict[str, Any]
    elapsed_ms: float
    timestamp: str = field(default_factory=utc_now_iso)


@dataclass
class TraceContext:
    """Request-scoped trace context."""

    trace_type: str
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)
    stages: list[TraceStage] = field(default_factory=list)
    finished_at: str | None = None
    _start_mono: float = field(default_factory=time.monotonic, repr=False)

    def record_stage(self, name: str, data: dict[str, Any], elapsed_ms: float) -> None:
        """Append a stage entry."""
        self.stages.append(TraceStage(name=name, data=data, elapsed_ms=round(elapsed_ms, 2)))

    def finish(self) -> None:
        """Mark the trace as finished."""
        self.finished_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the trace to a dictionary."""
        total_elapsed_ms = (time.monotonic() - self._start_mono) * 1000.0
        return {
            "trace_id": self.trace_id,
            "trace_type": self.trace_type,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_elapsed_ms": round(total_elapsed_ms, 2),
            "metadata": self.metadata,
            "stages": [
                {
                    "name": stage.name,
                    "elapsed_ms": stage.elapsed_ms,
                    "timestamp": stage.timestamp,
                    "data": stage.data,
                }
                for stage in self.stages
            ],
        }


class JsonlTraceCollector:
    """Persist traces to a JSONL file."""

    def __init__(self, target_path: str | Path) -> None:
        self.target_path = Path(target_path)
        self.target_path.parent.mkdir(parents=True, exist_ok=True)

    def collect(self, trace: TraceContext) -> None:
        """Append a finished trace to disk."""
        if trace.finished_at is None:
            trace.finish()
        with self.target_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(trace.to_dict(), ensure_ascii=False) + "\n")
