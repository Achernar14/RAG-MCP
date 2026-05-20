"""Official MCP SDK server wiring."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from rag_mcp.application.dto.models import (
    CollectionInfoResponse,
    DeleteDocumentResponse,
    DocumentDetailResponse,
    DocumentListItemResponse,
    DocumentSummaryResponse,
    EvaluationReportDetailResponse,
    EvaluationReportListItemResponse,
    EvaluationRunRequest,
    GenerateAnswerRequest,
    GenerateAnswerResponse,
    IngestRequest,
    IngestResponse,
    KnowledgeStatusResponse,
    QueryRequest,
    QueryResponse,
    RebuildCollectionResponse,
    TraceDetailResponse,
    TraceListItemResponse,
)
from rag_mcp.core.container import get_container


TopK = Annotated[int, Field(ge=1, le=20)]
TraceLimit = Annotated[int, Field(ge=1, le=100)]


def knowledge_query(
    query: Annotated[str, Field(min_length=1)],
    top_k: TopK = 5,
) -> QueryResponse:
    """Run hybrid retrieval over the active knowledge base."""
    return get_container().query_use_case.execute(QueryRequest(query=query, top_k=top_k))


def generate_answer(
    query: Annotated[str, Field(min_length=1)],
    top_k: TopK = 5,
) -> GenerateAnswerResponse:
    """Generate a grounded answer with citations from retrieved knowledge sources."""
    return get_container().generate_answer_use_case.execute(
        GenerateAnswerRequest(query=query, top_k=top_k)
    )


def knowledge_ingest(
    path: Annotated[str, Field(min_length=1)],
    force_rebuild: bool = False,
) -> IngestResponse:
    """Ingest a local document into the active knowledge base."""
    return get_container().ingest_use_case.execute(
        IngestRequest(path=path, force_rebuild=force_rebuild)
    )


def knowledge_status() -> KnowledgeStatusResponse:
    """Return high-level status for the active knowledge base."""
    return get_container().knowledge_status_use_case.execute()


def list_documents() -> list[DocumentListItemResponse]:
    """List documents that are currently ingested."""
    return get_container().list_documents_use_case.execute()


def list_traces(
    trace_type: str | None = None,
    limit: TraceLimit = 20,
) -> list[TraceListItemResponse]:
    """List persisted traces with optional trace-type filtering."""
    return get_container().list_traces_use_case.execute(trace_type=trace_type, limit=limit)


def get_trace_detail(
    trace_id: Annotated[str, Field(min_length=1)],
) -> TraceDetailResponse:
    """Get a single persisted trace by trace id."""
    return get_container().get_trace_detail_use_case.execute(trace_id)


def list_collections() -> list[CollectionInfoResponse]:
    """List the active logical collections and index statistics."""
    return get_container().list_collections_use_case.execute()


def run_evaluation(
    dataset_path: str | None = None,
    top_k: TopK | None = None,
) -> EvaluationReportDetailResponse:
    """Run retrieval evaluation against the configured golden dataset."""
    return get_container().run_evaluation_use_case.execute(
        EvaluationRunRequest(dataset_path=dataset_path, top_k=top_k)
    )


def list_evaluation_reports(
    limit: TraceLimit = 20,
) -> list[EvaluationReportListItemResponse]:
    """List recent persisted evaluation reports."""
    return get_container().list_evaluation_reports_use_case.execute(limit=limit)


def get_evaluation_report(
    report_id: Annotated[str, Field(min_length=1)],
) -> EvaluationReportDetailResponse:
    """Get a single evaluation report by report id."""
    return get_container().get_evaluation_report_detail_use_case.execute(report_id)


def rebuild_collection(
    collection_name: str | None = None,
) -> RebuildCollectionResponse:
    """Rebuild indexes for the active collection from persisted source documents."""
    return get_container().rebuild_collection_use_case.execute(collection_name)


def get_document_detail(
    document_id: Annotated[str, Field(min_length=1)],
) -> DocumentDetailResponse:
    """Get a detailed document view including chunk breakdown."""
    return get_container().get_document_detail_use_case.execute(document_id)


def get_document_summary(
    document_id: Annotated[str, Field(min_length=1)],
) -> DocumentSummaryResponse:
    """Get a summary view for a document."""
    return get_container().get_document_summary_use_case.execute(document_id)


def delete_document(
    document_id: Annotated[str, Field(min_length=1)],
) -> DeleteDocumentResponse:
    """Delete a document and remove its vector and sparse index entries."""
    return get_container().delete_document_use_case.execute(document_id)


SDK_TOOLS = [
    knowledge_query,
    generate_answer,
    knowledge_ingest,
    knowledge_status,
    list_documents,
    list_traces,
    get_trace_detail,
    list_collections,
    run_evaluation,
    list_evaluation_reports,
    get_evaluation_report,
    rebuild_collection,
    get_document_detail,
    get_document_summary,
    delete_document,
]


def _build_fastmcp_server() -> FastMCP:
    """Build an official SDK-based MCP server."""
    settings = get_container().settings
    server = FastMCP(name=settings.mcp.server_name)
    # FastMCP does not expose a public version constructor argument, so we
    # set the underlying low-level server version to keep initialize()
    # aligned with our configured MCP metadata.
    server._mcp_server.version = settings.mcp.server_version
    for tool in SDK_TOOLS:
        server.add_tool(tool, name=tool.__name__, structured_output=True)
    return server


@lru_cache(maxsize=1)
def create_fastmcp_server() -> FastMCP:
    """Return the shared official SDK-based MCP server instance."""
    return _build_fastmcp_server()


def reset_fastmcp_server() -> None:
    """Clear the cached SDK server instance."""
    create_fastmcp_server.cache_clear()


def main() -> int:
    """Run the SDK-backed MCP stdio server."""
    create_fastmcp_server().run(transport="stdio")
    return 0
