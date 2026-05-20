"""Collection rebuild use case."""

from __future__ import annotations

import time

from rag_mcp.application.dto.models import RebuildCollectionResponse
from rag_mcp.application.dto.models import RebuildFailureResponse
from rag_mcp.core.exceptions import NotFoundError
from rag_mcp.core.tracing import TraceContext


class RebuildCollectionUseCase:
    """Rebuild all document indexes for the active logical collection."""

    def __init__(self, settings, document_repository, pipeline, trace_collector) -> None:
        self.settings = settings
        self.document_repository = document_repository
        self.pipeline = pipeline
        self.trace_collector = trace_collector

    def execute(self, collection_name: str | None = None) -> RebuildCollectionResponse:
        """Rebuild the configured collection document-by-document."""
        active_collection = self.settings.vector_store.collection_name
        if collection_name and collection_name != active_collection:
            raise NotFoundError(f"Collection not found: {collection_name}")

        documents = list(self.document_repository.list_all())
        failures: list[RebuildFailureResponse] = []
        rebuilt_count = 0

        for document in documents:
            trace = TraceContext(
                trace_type="ingestion",
                metadata={
                    "path": document.source_path,
                    "document_id": document.id,
                    "collection_name": active_collection,
                    "rebuild": True,
                },
            )
            started = time.monotonic()
            try:
                self.pipeline.rebuild(document.source_path, trace)
                rebuilt_count += 1
            except Exception as exc:
                failures.append(
                    RebuildFailureResponse(
                        document_id=document.id,
                        source_path=document.source_path,
                        error=str(exc),
                    )
                )
                trace.record_stage(
                    "rebuild_failed",
                    {"error": str(exc)},
                    (time.monotonic() - started) * 1000.0,
                )
                trace.finish()
                self.trace_collector.collect(trace)

        return RebuildCollectionResponse(
            collection_name=active_collection,
            requested_document_count=len(documents),
            rebuilt_document_count=rebuilt_count,
            failed_document_count=len(failures),
            failures=failures,
            trace_id=None,
        )
