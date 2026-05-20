"""Query use case."""

from __future__ import annotations

from rag_mcp.application.dto.models import (
    QueryRequest,
    QueryResponse,
    QueryResultDto,
    QuerySourceDto,
)
from rag_mcp.core.tracing import TraceContext
from rag_mcp.domain.entities.models import SourceTrace


class QueryKnowledgeUseCase:
    """Execute dense retrieval against the knowledge base."""

    def __init__(self, retrieval_service, trace_collector) -> None:
        self.retrieval_service = retrieval_service
        self.trace_collector = trace_collector

    def execute(self, request: QueryRequest) -> QueryResponse:
        """Run the query flow and map to response DTO."""
        trace = TraceContext(
            trace_type="query",
            metadata={"query": request.query, "top_k": request.top_k},
        )
        results = self.retrieval_service.search(
            query=request.query,
            top_k=request.top_k,
            trace=trace,
        )
        sources = self._build_sources(results)
        trace.finish()
        self.trace_collector.collect(trace)
        return QueryResponse(
            query=request.query,
            results=[
                QueryResultDto(
                    chunk_id=result.chunk_id,
                    score=result.score,
                    text=result.text,
                    source_path=str(result.metadata.get("source_path", "")),
                    retrieval_method=result.retrieval_method,
                )
                for result in results
            ],
            sources=[
                QuerySourceDto(
                    index=source.index,
                    chunk_id=source.chunk_id,
                    document_id=source.document_id,
                    source_path=source.source_path,
                    score=source.score,
                    snippet=source.snippet,
                    chunk_index=source.chunk_index,
                )
                for source in sources
            ],
            trace_id=trace.trace_id,
            rerank_applied=any(
                result.retrieval_method and "rerank" in result.retrieval_method
                for result in results
            ),
        )

    def _build_sources(self, results) -> list[SourceTrace]:
        sources: list[SourceTrace] = []
        for index, result in enumerate(results, start=1):
            metadata = result.metadata
            sources.append(
                SourceTrace(
                    index=index,
                    chunk_id=result.chunk_id,
                    document_id=str(metadata.get("document_id", "")),
                    source_path=str(metadata.get("source_path", "")),
                    score=result.score,
                    snippet=result.text[:200],
                    chunk_index=metadata.get("chunk_index"),
                )
            )
        return sources
