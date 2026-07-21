"""FastAPI routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from rag_mcp.api.auth import verify_api_key
from rag_mcp.application.dto.models import (
    EvaluationRunRequest,
    GenerateAnswerRequest,
    IngestRequest,
    QueryRequest,
)
from rag_mcp.application.handlers import (
    delete_document,
    generate_answer,
    generate_answer_stream,
    get_document_detail,
    get_document_summary,
    get_evaluation_report_detail,
    get_knowledge_status,
    get_trace_detail,
    ingest_document,
    list_collections,
    list_documents,
    list_evaluation_reports,
    list_traces,
    rebuild_collection,
    run_evaluation,
    search_knowledge,
)
from rag_mcp.core.exceptions import IngestionError, NotFoundError
from rag_mcp.factory import get_rag

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])


def _require_skill(name: str) -> None:
    rag = get_rag()
    if not getattr(rag.settings.skills, name, False):
        raise HTTPException(status_code=404, detail=f"Skill '{name}' is not enabled")


# ── Health ──────────────────────────────────────────────────────────────


@router.get("/health")
def health() -> dict:
    return {"code": 0, "message": "ok", "data": {"status": "healthy"}, "trace_id": None}


# ── Ingestion ───────────────────────────────────────────────────────────


@router.post("/ingest")
def ingest(request: IngestRequest) -> dict:
    _require_skill("ingestion")
    try:
        result = ingest_document(
            get_rag(), request.path,
            force_rebuild=request.force_rebuild,
            collection_name=request.collection_name,
        )
    except IngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": result, "trace_id": result["trace_id"]}


@router.get("/stats")
def stats(collection_name: str | None = None) -> dict:
    _require_skill("ingestion")
    result = get_knowledge_status(get_rag(), collection_name)
    return {"code": 0, "message": "ok", "data": result, "trace_id": None}


@router.post("/collections/rebuild")
def collections_rebuild(collection_name: str | None = None) -> dict:
    _require_skill("ingestion")
    try:
        result = rebuild_collection(get_rag(), collection_name)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": result, "trace_id": None}


@router.get("/collections")
def collections_list() -> dict:
    _require_skill("ingestion")
    result = list_collections(get_rag())
    return {"code": 0, "message": "ok", "data": result, "trace_id": None}


# ── Retrieval ───────────────────────────────────────────────────────────


@router.post("/query")
def query_knowledge(request: QueryRequest) -> dict:
    _require_skill("retrieval")
    result = search_knowledge(get_rag(), request.query, request.top_k)
    return {"code": 0, "message": "ok", "data": result, "trace_id": result["trace_id"]}


# ── Generation ──────────────────────────────────────────────────────────


@router.post("/answers/generate")
def generate(request: GenerateAnswerRequest) -> dict:
    _require_skill("generation")
    result = generate_answer(get_rag(), request.query, request.top_k,
                             request.collection_name)
    return {"code": 0, "message": "ok", "data": result, "trace_id": result["trace_id"]}


@router.post("/answers/stream")
def generate_stream(request: GenerateAnswerRequest):
    _require_skill("generation")

    def _sse_generator():
        for event in generate_answer_stream(get_rag(), request.query,
                                            request.top_k, request.collection_name):
            event_type = event["event"]
            payload = json.dumps(event["data"], ensure_ascii=False)
            yield f"event: {event_type}\ndata: {payload}\n\n"

    return StreamingResponse(
        _sse_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )


# ── Document management ─────────────────────────────────────────────────


@router.get("/documents")
def documents_list(collection_name: str | None = None) -> dict:
    _require_skill("document_management")
    result = list_documents(get_rag(), collection_name)
    return {"code": 0, "message": "ok", "data": result, "trace_id": None}


@router.get("/documents/{document_id}")
def documents_summary(document_id: str, collection_name: str | None = None) -> dict:
    _require_skill("document_management")
    try:
        result = get_document_summary(get_rag(), document_id, collection_name)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": result, "trace_id": None}


@router.get("/documents/{document_id}/detail")
def documents_detail(document_id: str, collection_name: str | None = None) -> dict:
    _require_skill("document_management")
    try:
        result = get_document_detail(get_rag(), document_id, collection_name)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": result, "trace_id": None}


@router.delete("/documents/{document_id}")
def documents_delete(document_id: str, collection_name: str | None = None) -> dict:
    _require_skill("document_management")
    try:
        result = delete_document(get_rag(), document_id, collection_name)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": result, "trace_id": None}


# ── Evaluation ──────────────────────────────────────────────────────────


@router.post("/evaluations/run")
def evaluations_run(request: EvaluationRunRequest) -> dict:
    _require_skill("evaluation")
    result = run_evaluation(get_rag(), request.dataset_path, request.top_k)
    return {"code": 0, "message": "ok", "data": result, "trace_id": result["trace_id"]}


@router.get("/evaluations")
def evaluations_list(limit: int = 20) -> dict:
    _require_skill("evaluation")
    result = list_evaluation_reports(get_rag(), limit)
    return {"code": 0, "message": "ok", "data": result, "trace_id": None}


@router.get("/evaluations/{report_id}")
def evaluations_detail(report_id: str) -> dict:
    _require_skill("evaluation")
    try:
        result = get_evaluation_report_detail(get_rag(), report_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": result, "trace_id": None}


# ── Observability ───────────────────────────────────────────────────────


@router.get("/traces")
def traces_list(trace_type: str | None = None, limit: int = 20) -> dict:
    _require_skill("observability")
    result = list_traces(get_rag(), trace_type, limit)
    return {"code": 0, "message": "ok", "data": result, "trace_id": None}


@router.get("/traces/{trace_id}")
def traces_detail(trace_id: str) -> dict:
    _require_skill("observability")
    try:
        result = get_trace_detail(get_rag(), trace_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": result, "trace_id": None}
