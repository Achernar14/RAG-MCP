"""JSONL-backed trace repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonlTraceRepository:
    """Read persisted traces from the local JSONL trace log."""

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def list_traces(self, trace_type: str | None = None, limit: int | None = 20) -> list[dict[str, Any]]:
        """Return recent traces, optionally filtered by type."""
        traces = self._load_all()
        if trace_type:
            traces = [item for item in traces if item.get("trace_type") == trace_type]
        traces.sort(
            key=lambda item: (
                item.get("finished_at") or item.get("started_at") or "",
                item.get("trace_id") or "",
            ),
            reverse=True,
        )
        if limit is None:
            return traces
        return traces[:limit]

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        """Return a single trace by id if present."""
        for item in self._load_all():
            if item.get("trace_id") == trace_id:
                return item
        return None

    def _load_all(self) -> list[dict[str, Any]]:
        if not self.file_path.exists():
            return []

        payload: list[dict[str, Any]] = []
        with self.file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                payload.append(json.loads(raw))
        return payload
