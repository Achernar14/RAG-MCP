"""Minimal ingestion pipeline for the MVP."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from rag_mcp.domain.entities.models import Document
from rag_mcp.domain.entities.models import ChunkRecord
from rag_mcp.infrastructure.ingestion.source_inspector import SourceInspection


@dataclass
class PipelineResult:
    """Ingestion outcome."""

    document_id: str
    chunk_count: int
    ingestion_action: str
    replaced_existing: bool = False


@dataclass
class PreparedIngestion:
    """Prepared ingestion artifacts before persistence."""

    document: Document
    chunks: list
    records: list[ChunkRecord]


@dataclass
class IngestionDecision:
    """Decision made after document loading and metadata comparison."""

    action: str
    existing_document: Document | None
    replaced_existing: bool = False


class IngestionPipeline:
    """Load, split, embed and store a document."""

    def __init__(
        self,
        loader,
        splitter,
        embedding_provider,
        document_repository,
        chunk_repository,
        vector_store,
        sparse_index,
        trace_collector,
        source_inspector=None,
        source_validator=None,
    ) -> None:
        self.loader = loader
        self.splitter = splitter
        self.embedding_provider = embedding_provider
        self.document_repository = document_repository
        self.chunk_repository = chunk_repository
        self.vector_store = vector_store
        self.sparse_index = sparse_index
        self.trace_collector = trace_collector
        self.source_inspector = source_inspector
        self.source_validator = source_validator

    def run(self, file_path: str, trace, *, replace_existing: bool = False) -> PipelineResult:
        """Execute the full MVP ingestion flow."""
        validated_path = self._validate_source(file_path, trace)
        precheck = self._precheck_skip(str(validated_path), trace, replace_existing=replace_existing)
        if precheck is not None:
            return precheck
        document = self._load_document(str(validated_path), trace)
        decision = self._decide_ingestion_action(document, trace, replace_existing=replace_existing)
        if decision.action == "skipped":
            return self._finish_skipped_ingestion(document, decision, trace)
        prepared = self.prepare(document, trace)
        return self.persist(prepared, trace, decision=decision)

    def rebuild(self, file_path: str, trace) -> PipelineResult:
        """Rebuild a document's stored indexes from the source file."""
        validated_path = self._validate_source(file_path, trace)
        document = self._load_document(str(validated_path), trace)
        decision = self._decide_ingestion_action(document, trace, replace_existing=True)
        prepared = self.prepare(document, trace)
        return self.persist(prepared, trace, decision=decision)

    def _validate_source(self, file_path: str, trace) -> Path:
        """Validate the local source file before any ingestion work starts."""
        if self.source_validator is None:
            return Path(file_path).resolve()
        start = time.monotonic()
        validated_path = self.source_validator.validate(file_path)
        trace.record_stage(
            "validate_source",
            {
                "source_path": str(validated_path),
                "extension": validated_path.suffix.lower(),
            },
            (time.monotonic() - start) * 1000.0,
        )
        return validated_path

    def _precheck_skip(self, file_path: str, trace, *, replace_existing: bool) -> PipelineResult | None:
        """Short-circuit unchanged sources before full loading/parsing."""
        if replace_existing or self.source_inspector is None:
            return None

        start = time.monotonic()
        inspection = self.source_inspector.inspect(file_path)
        trace.record_stage(
            "precheck",
            {
                "source_path": inspection.path,
                "source_size_bytes": inspection.size_bytes,
                "source_modified_at_ns": inspection.modified_at_ns,
            },
            (time.monotonic() - start) * 1000.0,
        )

        existing_document = self.document_repository.get_by_source_path(inspection.path)
        if existing_document is None:
            return None

        metadata = existing_document.metadata
        same_mtime = metadata.get("source_modified_at_ns") == inspection.modified_at_ns
        same_size = metadata.get("source_size_bytes") == inspection.size_bytes
        same_bytes = metadata.get("source_bytes_fingerprint") == inspection.bytes_fingerprint
        if not (same_mtime and same_size and same_bytes):
            return None

        trace.record_stage(
            "idempotency_check",
            {
                "ingestion_action": "skipped",
                "document_id": existing_document.id,
                "content_changed": False,
                "reason": "precheck_unchanged_source",
                "fingerprint_type": "source_bytes_fingerprint",
            },
            0.0,
        )
        trace.finish()
        self.trace_collector.collect(trace)
        return PipelineResult(
            document_id=existing_document.id,
            chunk_count=len(self.chunk_repository.list_by_document(existing_document.id)),
            ingestion_action="skipped",
            replaced_existing=False,
        )

    def _load_document(self, file_path: str, trace) -> Document:
        """Load a document and record enriched source metadata."""
        start = time.monotonic()
        document = self.loader.load(file_path)
        trace.record_stage(
            "load",
            {
                "document_id": document.id,
                "filename": document.filename,
                "source_size_bytes": document.metadata.get("source_size_bytes"),
                "source_modified_at_ns": document.metadata.get("source_modified_at_ns"),
            },
            (time.monotonic() - start) * 1000.0,
        )
        return document

    def prepare(self, document: Document, trace) -> PreparedIngestion:
        """Split and embed a loaded document without persisting it."""
        start = time.monotonic()
        chunks = self.splitter.split(document)
        trace.record_stage(
            "split",
            {"chunk_count": len(chunks)},
            (time.monotonic() - start) * 1000.0,
        )

        start = time.monotonic()
        vectors = self.embedding_provider.embed_texts([chunk.text for chunk in chunks])
        trace.record_stage(
            "embed",
            {"vector_count": len(vectors)},
            (time.monotonic() - start) * 1000.0,
        )

        records = [
            ChunkRecord(
                id=chunk.id,
                document_id=chunk.document_id,
                text=chunk.text,
                dense_vector=vector,
                metadata=chunk.metadata,
            )
            for chunk, vector in zip(chunks, vectors, strict=False)
        ]
        return PreparedIngestion(document=document, chunks=chunks, records=records)

    def _decide_ingestion_action(
        self,
        document: Document,
        trace,
        *,
        replace_existing: bool,
    ) -> IngestionDecision:
        """Decide whether to create, replace, or skip ingestion work."""
        existing_document = self.document_repository.get_by_source_path(document.source_path)
        if existing_document is None:
            action = "created"
            replaced_existing = False
            content_changed = False
            reason = "new_document"
        else:
            new_fingerprint = self._identity_fingerprint(document)
            existing_fingerprint = self._identity_fingerprint(existing_document)
            if not replace_existing and existing_fingerprint == new_fingerprint:
                action = "skipped"
                replaced_existing = False
                content_changed = False
                reason = "unchanged_source"
            else:
                action = "replaced"
                replaced_existing = True
                content_changed = existing_fingerprint != new_fingerprint
                reason = "explicit_rebuild" if replace_existing else "source_changed"
        trace.record_stage(
            "idempotency_check",
            {
                "ingestion_action": action,
                "document_id": existing_document.id if existing_document is not None else document.id,
                "content_changed": content_changed,
                "reason": reason,
                "fingerprint_type": "source_bytes_fingerprint",
            },
            0.0,
        )
        return IngestionDecision(
            action=action,
            existing_document=existing_document,
            replaced_existing=replaced_existing,
        )

    def _finish_skipped_ingestion(
        self,
        document: Document,
        decision: IngestionDecision,
        trace,
    ) -> PipelineResult:
        """Finalize a skipped ingestion without split/embed/upsert work."""
        existing_document = decision.existing_document
        chunk_count = 0
        document_id = document.id
        if existing_document is not None:
            document_id = existing_document.id
            chunk_count = len(self.chunk_repository.list_by_document(existing_document.id))
        trace.finish()
        self.trace_collector.collect(trace)
        return PipelineResult(
            document_id=document_id,
            chunk_count=chunk_count,
            ingestion_action=decision.action,
            replaced_existing=decision.replaced_existing,
        )

    def persist(self, prepared: PreparedIngestion, trace, decision: IngestionDecision) -> PipelineResult:
        """Persist a prepared ingestion payload to all local stores."""
        document = prepared.document
        existing_document = decision.existing_document
        if existing_document is not None:
            document.created_at = existing_document.created_at

        if decision.replaced_existing and existing_document is not None:
            start = time.monotonic()
            deleted_chunk_count = self.chunk_repository.delete_by_document(existing_document.id)
            deleted_vector_count = self.vector_store.delete_by_document(existing_document.id)
            deleted_sparse_count = self.sparse_index.delete_by_document(existing_document.id)
            trace.record_stage(
                "cleanup",
                {
                    "deleted_chunk_count": deleted_chunk_count,
                    "deleted_vector_count": deleted_vector_count,
                    "deleted_sparse_count": deleted_sparse_count,
                },
                (time.monotonic() - start) * 1000.0,
            )

        start = time.monotonic()
        self.document_repository.save(document)
        self.chunk_repository.save_many(prepared.chunks)
        self.vector_store.upsert(prepared.records)
        self.sparse_index.upsert(prepared.records)
        trace.record_stage(
            "upsert",
            {
                "record_count": len(prepared.records),
                "sparse_indexed": len(prepared.records),
                "replace_existing": decision.replaced_existing,
            },
            (time.monotonic() - start) * 1000.0,
        )
        trace.finish()
        self.trace_collector.collect(trace)
        return PipelineResult(
            document_id=document.id,
            chunk_count=len(prepared.chunks),
            ingestion_action=decision.action,
            replaced_existing=decision.replaced_existing,
        )

    def _identity_fingerprint(self, document: Document) -> str | None:
        """Return the best available fingerprint for idempotency decisions."""
        metadata = document.metadata
        return metadata.get("source_bytes_fingerprint") or metadata.get("content_fingerprint")
