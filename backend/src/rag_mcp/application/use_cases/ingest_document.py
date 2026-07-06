"""Document ingestion use case."""

from __future__ import annotations

from rag_mcp.application.dto.models import IngestRequest, IngestResponse
from rag_mcp.core.tracing import TraceContext


class IngestDocumentUseCase:
    """Run the ingestion pipeline for a single document."""

    def __init__(self, pipeline) -> None:
        self.pipeline = pipeline

    def execute(self, request: IngestRequest) -> IngestResponse:
        """Execute the ingestion flow."""
        trace = TraceContext(
            trace_type="ingestion",
            metadata={
                "path": request.path,
                "force_rebuild": request.force_rebuild,
                "collection_name": request.collection_name,
            },
        )
        result = self.pipeline.run(
            file_path=request.path,
            trace=trace,
            replace_existing=request.force_rebuild,
            collection_name=request.collection_name,
        )
        trace.finish()
        return IngestResponse(
            document_id=result.document_id,
            chunk_count=result.chunk_count,
            trace_id=trace.trace_id,
            ingestion_action=result.ingestion_action,
            replaced_existing=result.replaced_existing,
        )
