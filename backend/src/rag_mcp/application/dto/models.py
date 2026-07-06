"""Application DTOs for ingest and query use cases."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    """Input for the document ingestion use case."""

    path: str
    force_rebuild: bool = False
    collection_name: str | None = None


class IngestResponse(BaseModel):
    """Output for the document ingestion use case."""

    document_id: str
    chunk_count: int
    trace_id: str
    ingestion_action: str = "created"
    replaced_existing: bool = False


class QueryRequest(BaseModel):
    """Input for the query use case."""

    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    collection_name: str | None = None


class QuerySourceDto(BaseModel):
    """Structured source DTO returned to clients."""

    index: int
    chunk_id: str
    document_id: str
    source_path: str
    score: float
    snippet: str
    chunk_index: int | None = None


class QueryResultDto(BaseModel):
    """Single query result item."""

    chunk_id: str
    score: float
    text: str
    source_path: str
    retrieval_method: str | None = None


class QueryResponse(BaseModel):
    """Output for the query use case."""

    query: str
    results: list[QueryResultDto]
    sources: list[QuerySourceDto]
    trace_id: str
    rerank_applied: bool = False


class GenerateAnswerRequest(BaseModel):
    """Input for grounded answer generation."""

    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    collection_name: str | None = None


class GenerateAnswerResponse(BaseModel):
    """Output for grounded answer generation."""

    query: str
    answer: str
    results: list[QueryResultDto]
    sources: list[QuerySourceDto]
    trace_id: str
    rerank_applied: bool = False
    generated_by_llm: bool = True
    generation_error: str | None = None


class DocumentSummaryResponse(BaseModel):
    """Summary view of a document."""

    document_id: str
    filename: str
    source_path: str
    doc_type: str
    chunk_count: int
    summary: str
    trace_id: str | None = None


class DocumentListItemResponse(BaseModel):
    """List view of an ingested document."""

    id: str
    filename: str
    source_path: str
    doc_type: str
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class DocumentChunkDetailResponse(BaseModel):
    """Chunk detail view for document management."""

    chunk_id: str
    chunk_index: int
    start_offset: int
    end_offset: int
    text: str


class DocumentAssetDetailResponse(BaseModel):
    """Non-text asset detail view for multimodal document skeleton."""

    asset_id: str
    asset_type: str
    page_number: int | None = None
    storage_path: str | None = None
    caption: str | None = None
    status: str | None = None
    metadata: dict = Field(default_factory=dict)


class DocumentDetailResponse(BaseModel):
    """Detailed view of an ingested document."""

    document_id: str
    filename: str
    source_path: str
    doc_type: str
    content_length: int
    chunk_count: int
    created_at: datetime
    updated_at: datetime
    metadata: dict
    chunks: list[DocumentChunkDetailResponse]
    assets: list[DocumentAssetDetailResponse] = Field(default_factory=list)
    trace_id: str | None = None


class CollectionInfoResponse(BaseModel):
    """Summary view of a collection/index set."""

    name: str
    document_count: int
    chunk_count: int
    vector_store_provider: str
    sparse_index_present: bool


class TraceStageResponse(BaseModel):
    """A single trace stage entry."""

    name: str
    elapsed_ms: float
    timestamp: str
    data: dict


class TraceListItemResponse(BaseModel):
    """Summary view of a persisted trace."""

    trace_id: str
    trace_type: str
    started_at: str
    finished_at: str | None = None
    total_elapsed_ms: float
    metadata: dict


class TraceDetailResponse(BaseModel):
    """Detailed view of a persisted trace."""

    trace_id: str
    trace_type: str
    started_at: str
    finished_at: str | None = None
    total_elapsed_ms: float
    metadata: dict
    stages: list[TraceStageResponse]


class KnowledgeStatusResponse(BaseModel):
    """Operational status for the active knowledge base."""

    collection_name: str
    document_count: int
    chunk_count: int
    vector_store_provider: str
    embedding_provider: str
    sparse_index_present: bool


class RebuildFailureResponse(BaseModel):
    """Single document rebuild failure item."""

    document_id: str
    source_path: str
    error: str


class RebuildCollectionResponse(BaseModel):
    """Result of rebuilding the active collection indexes."""

    collection_name: str
    requested_document_count: int
    rebuilt_document_count: int
    failed_document_count: int
    failures: list[RebuildFailureResponse]
    trace_id: str | None = None


class DeleteDocumentResponse(BaseModel):
    """Result of deleting a document and its indexes."""

    document_id: str
    deleted_chunk_count: int
    trace_id: str | None = None


class EvaluationRunRequest(BaseModel):
    """Input for evaluation execution."""

    dataset_path: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)


class EvaluationCaseRequest(BaseModel):
    """Single golden test case definition."""

    case_id: str
    query: str = Field(min_length=1)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_source_paths: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class EvaluationDatasetRequest(BaseModel):
    """Golden test dataset payload."""

    dataset_name: str
    cases: list[EvaluationCaseRequest]


class EvaluationSummaryResponse(BaseModel):
    """Summary metrics for a report."""

    total_cases: int
    hit_rate: float
    mrr: float
    top_k: int
    passed_case_count: int
    failed_case_count: int


class EvaluationCaseResultResponse(BaseModel):
    """Per-case evaluation result."""

    case_id: str
    query: str
    retrieved_chunk_ids: list[str]
    matched_chunk_ids: list[str]
    hit: bool
    reciprocal_rank: float
    top_k: int
    trace_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class EvaluationReportListItemResponse(BaseModel):
    """Summary view of an evaluation report."""

    report_id: str
    dataset_path: str
    started_at: str
    finished_at: str | None = None
    total_cases: int
    hit_rate: float
    mrr: float
    top_k: int
    trace_id: str | None = None


class EvaluationReportDetailResponse(BaseModel):
    """Detailed evaluation report payload."""

    report_id: str
    dataset_path: str
    started_at: str
    finished_at: str | None = None
    summary: EvaluationSummaryResponse
    cases: list[EvaluationCaseResultResponse]
    trace_id: str | None = None
