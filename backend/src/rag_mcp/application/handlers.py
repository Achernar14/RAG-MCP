"""Thin orchestration functions — trace + service call + dict output.

These replace the old UseCase classes.  Each function takes a
:class:`RAGSystem` and the request parameters, manages a trace, calls
the appropriate domain service, and returns a dict ready for API
serialization.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

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


def get_knowledge_status(rag, collection_name: str | None = None) -> dict:
    scope = rag.collection_manager.get_scope(collection_name)
    doc_repo = scope.document_repository
    chunk_repo = scope.chunk_repository
    docs = doc_repo.list_all()
    return {
        "collection_name": scope.name,
        "document_count": len(docs),
        "chunk_count": sum(len(chunk_repo.list_by_document(d.id)) for d in docs),
        "vector_store_provider": rag.settings.vector_store.provider,
        "embedding_provider": rag.embedding_provider.__class__.__name__,
        "sparse_index_present": scope.sparse_index.exists(),
    }


def rebuild_collection(rag, collection_name: str | None = None) -> dict:
    name = collection_name or rag.settings.vector_store.collection_name
    available = rag.collection_manager.list_collections()
    if name not in available:
        raise NotFoundError(f"Collection not found: {name}")

    scope = rag.collection_manager.get_scope(name)
    documents = list(scope.document_repository.list_all())
    failures: list[dict] = []
    rebuilt_count = 0

    for document in documents:
        trace = TraceContext(trace_type="ingestion", metadata={
            "path": document.source_path, "document_id": document.id,
            "collection_name": name, "rebuild": True,
        })
        try:
            rag.pipeline.rebuild(document.source_path, trace, collection_name=name)
            rebuilt_count += 1
        except Exception as exc:
            failures.append({
                "document_id": document.id,
                "source_path": document.source_path,
                "error": str(exc),
            })

    return {
        "collection_name": name,
        "requested_document_count": len(documents),
        "rebuilt_document_count": rebuilt_count,
        "failed_document_count": len(failures),
        "failures": failures,
        "trace_id": None,
    }


def list_collections(rag) -> list[dict]:
    result: list[dict] = []
    for name in rag.collection_manager.list_collections():
        scope = rag.collection_manager.get_scope(name)
        documents = scope.document_repository.list_all()
        chunk_count = sum(
            len(scope.chunk_repository.list_by_document(doc.id))
            for doc in documents
        )
        result.append({
            "name": name,
            "document_count": len(documents),
            "chunk_count": chunk_count,
            "vector_store_provider": rag.settings.vector_store.provider,
            "sparse_index_present": scope.sparse_index.exists(),
        })
    return result


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
# Document management
# ═══════════════════════════════════════════════════════════════════════════


def list_documents(rag, collection_name: str | None = None) -> list[dict]:
    scope = rag.collection_manager.get_scope(collection_name)
    documents = sorted(
        scope.document_repository.list_all(),
        key=lambda item: item.updated_at, reverse=True,
    )
    return [{
        "id": d.id, "filename": d.filename, "source_path": d.source_path,
        "doc_type": d.doc_type,
        "chunk_count": len(scope.chunk_repository.list_by_document(d.id)),
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(),
    } for d in documents]


def get_document_summary(rag, document_id: str,
                         collection_name: str | None = None) -> dict:
    scope = rag.collection_manager.get_scope(collection_name)
    doc = scope.document_repository.get(document_id)
    if doc is None:
        raise NotFoundError(f"Document not found: {document_id}")
    chunks = scope.chunk_repository.list_by_document(document_id)
    normalized = " ".join(doc.content.split())
    summary = normalized if len(normalized) <= 240 else normalized[:237].rstrip() + "..."
    return {
        "document_id": doc.id, "filename": doc.filename,
        "source_path": doc.source_path, "doc_type": doc.doc_type,
        "chunk_count": len(chunks), "summary": summary, "trace_id": None,
    }


def get_document_detail(rag, document_id: str,
                        collection_name: str | None = None) -> dict:
    scope = rag.collection_manager.get_scope(collection_name)
    doc = scope.document_repository.get(document_id)
    if doc is None:
        raise NotFoundError(f"Document not found: {document_id}")
    chunks = sorted(
        scope.chunk_repository.list_by_document(document_id),
        key=lambda item: item.chunk_index,
    )
    return {
        "document_id": doc.id, "filename": doc.filename,
        "source_path": doc.source_path, "doc_type": doc.doc_type,
        "content_length": len(doc.content), "chunk_count": len(chunks),
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
        "metadata": doc.metadata,
        "chunks": [{
            "chunk_id": c.id, "chunk_index": c.chunk_index,
            "start_offset": c.start_offset, "end_offset": c.end_offset,
            "text": c.text,
        } for c in chunks],
        "assets": doc.metadata.get("assets", []),
        "trace_id": None,
    }


def delete_document(rag, document_id: str,
                    collection_name: str | None = None) -> dict:
    scope = rag.collection_manager.get_scope(collection_name)
    doc = scope.document_repository.get(document_id)
    if doc is None:
        raise NotFoundError(f"Document not found: {document_id}")
    deleted = scope.chunk_repository.delete_by_document(document_id)
    scope.vector_store.delete_by_document(document_id)
    scope.sparse_index.delete_by_document(document_id)
    scope.document_repository.delete(document_id)
    return {
        "document_id": document_id,
        "deleted_chunk_count": deleted,
        "trace_id": None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Evaluation
# ═══════════════════════════════════════════════════════════════════════════


def run_evaluation(rag, dataset_path: str | None = None,
                   top_k: int | None = None) -> dict:
    from rag_mcp.application.dto.models import QueryRequest
    from rag_mcp.infrastructure.evaluation.dataset_loader import load_evaluation_cases
    from rag_mcp.domain.entities.models import EvaluationCaseResult, EvaluationReport, EvaluationSummary

    dataset_path = dataset_path or rag.settings.evaluation.default_test_set_path
    top_k = top_k or rag.settings.evaluation.top_k
    trace = TraceContext(trace_type="evaluation",
                         metadata={"dataset_path": dataset_path, "top_k": top_k})

    cases = load_evaluation_cases(dataset_path)
    results: list[EvaluationCaseResult] = []
    for case in cases:
        qr = rag.query_use_case.execute(QueryRequest(query=case.query, top_k=top_k))
        retrieved_ids = [r.chunk_id for r in qr.results]
        expected = set(case.expected_chunk_ids)
        matched = [cid for cid in retrieved_ids if cid in expected]
        rr = 0.0
        for rank, cid in enumerate(retrieved_ids, start=1):
            if cid in expected:
                rr = 1.0 / rank
                break
        results.append(EvaluationCaseResult(
            case_id=case.case_id, query=case.query,
            retrieved_chunk_ids=retrieved_ids, matched_chunk_ids=matched,
            hit=len(matched) > 0, reciprocal_rank=rr, top_k=top_k,
            trace_id=qr.trace_id,
        ))

    passed = sum(1 for r in results if r.hit)
    total = len(results)
    summary = EvaluationSummary(
        total_cases=total,
        hit_rate=round(passed / total, 4) if total else 0.0,
        mrr=round(sum(r.reciprocal_rank for r in results) / total, 4) if total else 0.0,
        top_k=top_k, passed_case_count=passed, failed_case_count=total - passed,
    )
    report = EvaluationReport(dataset_path=dataset_path, summary=summary, cases=results)
    rag.evaluation_report_repository.save(report)
    trace.finish()
    rag.trace_collector.collect(trace)

    return {
        "report_id": report.report_id,
        "dataset_path": report.dataset_path,
        "started_at": report.started_at.isoformat(),
        "finished_at": report.finished_at.isoformat() if report.finished_at else None,
        "summary": {
            "total_cases": summary.total_cases,
            "hit_rate": summary.hit_rate, "mrr": summary.mrr,
            "top_k": summary.top_k,
            "passed_case_count": summary.passed_case_count,
            "failed_case_count": summary.failed_case_count,
        },
        "cases": [{
            "case_id": r.case_id, "query": r.query,
            "retrieved_chunk_ids": r.retrieved_chunk_ids,
            "matched_chunk_ids": r.matched_chunk_ids,
            "hit": r.hit, "reciprocal_rank": r.reciprocal_rank,
            "top_k": r.top_k, "trace_id": r.trace_id, "metadata": r.metadata,
        } for r in results],
        "trace_id": trace.trace_id,
    }


def list_evaluation_reports(rag, limit: int = 20) -> list[dict]:
    reports = rag.evaluation_report_repository.list_reports(limit=limit)
    return [{
        "report_id": r.report_id, "dataset_path": r.dataset_path,
        "started_at": r.started_at.isoformat(),
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "total_cases": r.summary.total_cases,
        "hit_rate": r.summary.hit_rate, "mrr": r.summary.mrr,
        "top_k": r.summary.top_k, "trace_id": r.trace_id,
    } for r in reports]


def get_evaluation_report_detail(rag, report_id: str) -> dict:
    report = rag.evaluation_report_repository.get(report_id)
    if report is None:
        raise NotFoundError(f"Evaluation report not found: {report_id}")
    return {
        "report_id": report.report_id, "dataset_path": report.dataset_path,
        "started_at": report.started_at.isoformat(),
        "finished_at": report.finished_at.isoformat() if report.finished_at else None,
        "summary": {
            "total_cases": report.summary.total_cases,
            "hit_rate": report.summary.hit_rate, "mrr": report.summary.mrr,
            "top_k": report.summary.top_k,
            "passed_case_count": report.summary.passed_case_count,
            "failed_case_count": report.summary.failed_case_count,
        },
        "cases": [{
            "case_id": r.case_id, "query": r.query,
            "retrieved_chunk_ids": r.retrieved_chunk_ids,
            "matched_chunk_ids": r.matched_chunk_ids,
            "hit": r.hit, "reciprocal_rank": r.reciprocal_rank,
            "top_k": r.top_k, "trace_id": r.trace_id, "metadata": r.metadata,
        } for r in report.cases],
        "trace_id": report.trace_id,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Observability
# ═══════════════════════════════════════════════════════════════════════════


def list_traces(rag, trace_type: str | None = None, limit: int = 20) -> list[dict]:
    normalized_limit = max(1, min(limit, 100))
    payload = rag.trace_repository.list_traces(
        trace_type=trace_type, limit=normalized_limit)
    return [{
        "trace_id": item["trace_id"], "trace_type": item["trace_type"],
        "started_at": item["started_at"],
        "finished_at": item.get("finished_at"),
        "total_elapsed_ms": float(item.get("total_elapsed_ms", 0.0)),
        "metadata": item.get("metadata", {}),
    } for item in payload]


def get_trace_detail(rag, trace_id: str) -> dict:
    payload = rag.trace_repository.get_trace(trace_id)
    if payload is None:
        raise NotFoundError(f"Trace not found: {trace_id}")
    return {
        "trace_id": payload["trace_id"], "trace_type": payload["trace_type"],
        "started_at": payload["started_at"],
        "finished_at": payload.get("finished_at"),
        "total_elapsed_ms": float(payload.get("total_elapsed_ms", 0.0)),
        "metadata": payload.get("metadata", {}),
        "stages": [{
            "name": s["name"],
            "elapsed_ms": float(s.get("elapsed_ms", 0.0)),
            "timestamp": s["timestamp"],
            "data": s.get("data", {}),
        } for s in payload.get("stages", [])],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _build_sources(results) -> list[SourceTrace]:
    sources = []
    for index, result in enumerate(results, start=1):
        metadata = result.metadata
        sources.append(SourceTrace(
            index=index, chunk_id=result.chunk_id,
            document_id=str(metadata.get("document_id", "")),
            source_path=str(metadata.get("source_path", "")),
            score=result.score, snippet=result.text[:200],
            chunk_index=metadata.get("chunk_index"),
        ))
    return sources


def _result_to_dict(r) -> dict:
    return {
        "chunk_id": r.chunk_id, "score": r.score, "text": r.text,
        "source_path": str(r.metadata.get("source_path", "")),
        "retrieval_method": r.retrieval_method,
    }


def _source_to_dict(s: SourceTrace) -> dict:
    return {
        "index": s.index, "chunk_id": s.chunk_id,
        "document_id": s.document_id, "source_path": s.source_path,
        "score": s.score, "snippet": s.snippet, "chunk_index": s.chunk_index,
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
