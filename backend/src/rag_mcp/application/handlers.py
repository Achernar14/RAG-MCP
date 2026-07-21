"""Thin orchestration functions — trace + service call + dict output.

These replace the old UseCase classes.  Each function takes a
:class:`RAGSystem` and the request parameters, manages a trace, calls
the appropriate domain service, and returns a dict ready for API
serialization.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

from rag_mcp.application.dto.models import (
    DocumentDetailResponse,
    DocumentListItemResponse,
    DocumentSummaryResponse,
    EvaluationRunRequest,
    GenerateAnswerRequest,
    IngestRequest,
    QueryRequest,
)
from rag_mcp.core.exceptions import NotFoundError, ProviderError
from rag_mcp.core.tracing import TraceContext
from rag_mcp.domain.entities.models import SourceTrace


# ═══════════════════════════════════════════════════════════════════════════
# Ingestion
# ═══════════════════════════════════════════════════════════════════════════


def ingest_document(rag, path: str, force_rebuild: bool = False,
                    collection_name: str | None = None) -> dict:
    trace = TraceContext(trace_type="ingestion", metadata={
        "path": path, "force_rebuild": force_rebuild,
        "collection_name": collection_name,
    })
    result = rag.pipeline.run(
        file_path=path, trace=trace,
        replace_existing=force_rebuild, collection_name=collection_name,
    )
    return {
        "document_id": result.document_id,
        "chunk_count": result.chunk_count,
        "trace_id": trace.trace_id,
        "ingestion_action": result.ingestion_action,
        "replaced_existing": result.replaced_existing,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Retrieval
# ═══════════════════════════════════════════════════════════════════════════


def search_knowledge(rag, query: str, top_k: int = 5) -> dict:
    trace = TraceContext(trace_type="query",
                         metadata={"query": query, "top_k": top_k})
    results = rag.retrieval_service.search(query=query, top_k=top_k, trace=trace)
    sources = _build_sources(results)
    trace.finish()
    rag.trace_collector.collect(trace)
    return {
        "query": query,
        "results": [_result_to_dict(r) for r in results],
        "sources": [_source_to_dict(s) for s in sources],
        "trace_id": trace.trace_id,
        "rerank_applied": any(
            r.retrieval_method and "rerank" in r.retrieval_method
            for r in results
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Answer generation
# ═══════════════════════════════════════════════════════════════════════════


def generate_answer(rag, query: str, top_k: int = 5,
                    collection_name: str | None = None) -> dict:
    query_result = search_knowledge(rag, query, top_k)
    source_payload = query_result["sources"]

    rendered = rag.answer_prompt_builder.build(
        query=query, source_items=source_payload)

    trace = TraceContext(trace_type="answer_generation", metadata={
        "query": query, "top_k": top_k,
        "query_trace_id": query_result["trace_id"],
        "llm_provider": rag.llm_provider.__class__.__name__,
    })

    generation_started = time.monotonic()
    try:
        answer = rag.llm_provider.generate(
            rendered.user_prompt, system_prompt=rendered.system_prompt,
            metadata={"query": query, "sources": source_payload})
        generated_by_llm = True
        generation_error = None
    except ProviderError as exc:
        answer = _build_fallback_answer(query_result)
        generated_by_llm = False
        generation_error = str(exc)

    trace.record_stage("llm_generate", {
        "provider": rag.llm_provider.__class__.__name__,
        "fallback": generation_error is not None,
        "source_count": len(source_payload),
        **({"error": generation_error} if generation_error else {}),
    }, (time.monotonic() - generation_started) * 1000.0)
    trace.finish()
    rag.trace_collector.collect(trace)

    return {
        "query": query,
        "answer": answer,
        "results": query_result["results"],
        "sources": query_result["sources"],
        "trace_id": trace.trace_id,
        "rerank_applied": query_result["rerank_applied"],
        "generated_by_llm": generated_by_llm,
        "generation_error": generation_error,
    }


def generate_answer_stream(rag, query: str, top_k: int = 5,
                           collection_name: str | None = None) -> Iterator[dict]:
    query_result = search_knowledge(rag, query, top_k)
    source_payload = query_result["sources"]

    rendered = rag.answer_prompt_builder.build(
        query=query, source_items=source_payload)

    trace = TraceContext(trace_type="answer_generation", metadata={
        "query": query, "top_k": top_k,
        "query_trace_id": query_result["trace_id"],
        "llm_provider": rag.llm_provider.__class__.__name__,
    })

    yield {"event": "meta", "data": {
        "trace_id": trace.trace_id,
        "rerank_applied": query_result["rerank_applied"],
    }}
    yield {"event": "sources", "data": {"sources": source_payload}}

    generated_by_llm = False
    generation_error = None
    generation_started = time.monotonic()

    try:
        for token in rag.llm_provider.generate_stream(
            rendered.user_prompt, system_prompt=rendered.system_prompt,
            metadata={"query": query, "sources": source_payload}):
            generated_by_llm = True
            yield {"event": "token", "data": {"delta": token}}

        trace.record_stage("llm_generate", {
            "provider": rag.llm_provider.__class__.__name__,
            "source_count": len(source_payload),
        }, (time.monotonic() - generation_started) * 1000.0)
        trace.finish()
        rag.trace_collector.collect(trace)
        yield {"event": "done", "data": {
            "trace_id": trace.trace_id, "generated_by_llm": True,
        }}
    except ProviderError as exc:
        generation_error = str(exc)
        fallback = _build_fallback_answer(query_result)
        if fallback:
            yield {"event": "token", "data": {"delta": fallback}}
        trace.record_stage("llm_generate", {
            "provider": rag.llm_provider.__class__.__name__,
            "fallback": True, "source_count": len(source_payload),
            "error": generation_error,
        }, (time.monotonic() - generation_started) * 1000.0)
        trace.finish()
        rag.trace_collector.collect(trace)
        yield {"event": "error", "data": {
            "trace_id": trace.trace_id, "generated_by_llm": False,
            "error": generation_error,
        }}


# ═══════════════════════════════════════════════════════════════════════════
# Knowledge status
# ═══════════════════════════════════════════════════════════════════════════


def get_knowledge_status(rag, collection_name: str | None = None) -> dict:
    scope = rag.collection_manager.get_scope(collection_name)
    doc_repo = scope.document_repository
    chunk_repo = scope.chunk_repository
    docs = doc_repo.list_all()
    return {
        "collection_name": scope.name,
        "document_count": len(docs),
        "chunk_count": sum(
            len(chunk_repo.list_by_document(d.id)) for d in docs
        ),
        "vector_store_provider": rag.settings.vector_store.provider,
        "embedding_provider": rag.embedding_provider.__class__.__name__,
        "sparse_index_present": scope.sparse_index.exists(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _build_sources(results) -> list[SourceTrace]:
    sources = []
    for index, result in enumerate(results, start=1):
        metadata = result.metadata
        sources.append(SourceTrace(
            index=index,
            chunk_id=result.chunk_id,
            document_id=str(metadata.get("document_id", "")),
            source_path=str(metadata.get("source_path", "")),
            score=result.score,
            snippet=result.text[:200],
            chunk_index=metadata.get("chunk_index"),
        ))
    return sources


def _result_to_dict(r) -> dict:
    return {
        "chunk_id": r.chunk_id,
        "score": r.score,
        "text": r.text,
        "source_path": str(r.metadata.get("source_path", "")),
        "retrieval_method": r.retrieval_method,
    }


def _source_to_dict(s: SourceTrace) -> dict:
    return {
        "index": s.index, "chunk_id": s.chunk_id,
        "document_id": s.document_id, "source_path": s.source_path,
        "score": s.score, "snippet": s.snippet,
        "chunk_index": s.chunk_index,
    }


def _build_fallback_answer(query_result: dict) -> str:
    sources = query_result.get("sources", [])
    if not sources:
        return f"未能基于检索结果生成回答：{query_result.get('query', '')}"
    snippets = [s.get("snippet", "").strip() for s in sources[:2]
                if s.get("snippet", "").strip()]
    if not snippets:
        return f"未能基于检索结果生成回答：{query_result.get('query', '')}"
    return "基于检索结果的降级回答：\n" + "\n".join(
        f"{i}. {s}" for i, s in enumerate(snippets, start=1)
    )
