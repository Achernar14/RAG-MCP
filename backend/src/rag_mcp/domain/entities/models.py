"""Core domain models for RAG MCP."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


@dataclass
class Document:
    """A source document stored in the system."""

    id: str
    source_path: str
    filename: str
    doc_type: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class Chunk:
    """A chunk derived from a document."""

    id: str
    document_id: str
    text: str
    chunk_index: int
    start_offset: int
    end_offset: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkRecord:
    """A chunk prepared for storage and retrieval."""

    id: str
    document_id: str
    text: str
    dense_vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """A normalized retrieval hit."""

    chunk_id: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    retrieval_method: str | None = None


@dataclass
class SourceTrace:
    """A structured source trace for results and answers."""

    index: int
    chunk_id: str
    document_id: str
    source_path: str
    score: float
    snippet: str
    chunk_index: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationCase:
    """A single golden evaluation case."""

    case_id: str
    query: str
    expected_chunk_ids: list[str] = field(default_factory=list)
    expected_document_ids: list[str] = field(default_factory=list)
    expected_source_paths: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationCaseResult:
    """Per-case evaluation result."""

    case_id: str
    query: str
    retrieved_chunk_ids: list[str]
    matched_chunk_ids: list[str]
    hit: bool
    reciprocal_rank: float
    top_k: int
    trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationSummary:
    """Aggregated metrics for an evaluation run."""

    total_cases: int
    hit_rate: float
    mrr: float
    top_k: int
    passed_case_count: int
    failed_case_count: int


@dataclass
class EvaluationReport:
    """A persisted evaluation report."""

    dataset_path: str
    summary: EvaluationSummary
    cases: list[EvaluationCaseResult]
    trace_id: str | None = None
    report_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
