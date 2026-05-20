"""Golden evaluation dataset loading helpers."""

from __future__ import annotations

import json
from pathlib import Path

from rag_mcp.core.exceptions import EvaluationError
from rag_mcp.domain.entities.models import EvaluationCase


def load_evaluation_cases(dataset_path: str | Path) -> list[EvaluationCase]:
    """Load evaluation cases from a JSON dataset file."""
    path = Path(dataset_path)
    if not path.exists():
        raise EvaluationError(f"Evaluation dataset not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    cases = raw.get("cases")
    if not isinstance(cases, list):
        raise EvaluationError("Evaluation dataset must contain a 'cases' list")

    loaded: list[EvaluationCase] = []
    for item in cases:
        loaded.append(
            EvaluationCase(
                case_id=str(item["case_id"]),
                query=str(item["query"]),
                expected_chunk_ids=[str(value) for value in item.get("expected_chunk_ids", [])],
                expected_document_ids=[
                    str(value) for value in item.get("expected_document_ids", [])
                ],
                expected_source_paths=[
                    str(value) for value in item.get("expected_source_paths", [])
                ],
                metadata=item.get("metadata", {}) or {},
            )
        )
    return loaded
