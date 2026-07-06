"""Collection rebuild use case."""

from __future__ import annotations

import time

from rag_mcp.application.dto.models import RebuildCollectionResponse
from rag_mcp.application.dto.models import RebuildFailureResponse
from rag_mcp.core.exceptions import NotFoundError
from rag_mcp.core.tracing import TraceContext


class RebuildCollectionUseCase:
    """Rebuild all document indexes for a collection."""

    def __init__(self, settings, collection_manager, pipeline, trace_collector) -> None:
        self.settings = settings
        self.collection_manager = collection_manager
        self.pipeline = pipeline
        self.trace_collector = trace_collector

    def execute(self, collection_name: str | None = None) -> RebuildCollectionResponse:
        """Rebuild indexes for *collection_name* (or the default collection)."""
        name = collection_name or self.settings.vector_store.collection_name
        available = self.collection_manager.list_collections()
        if name not in available:
            raise NotFoundError(f"Collection not found: {name}")

        scope = self.collection_manager.get_scope(name)
        documents = list(scope.document_repository.list_all())
        failures: list[RebuildFailureResponse] = []
        rebuilt_count = 0

        for document in documents:
            trace = TraceContext(
                trace_type="ingestion",
                metadata={
                    "path": document.source_path,
                    "document_id": document.id,
                    "collection_name": name,
                    "rebuild": True,
                },
            )
            started = time.monotonic()
            try:
                self.pipeline.rebuild(document.source_path, trace, collection_name=name)
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
            collection_name=name,
            requested_document_count=len(documents),
            rebuilt_document_count=rebuilt_count,
            failed_document_count=len(failures),
            failures=failures,
            trace_id=None,
        )
