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
    generate_answer,
    generate_answer_stream,
    get_knowledge_status,
    ingest_document,
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
def rebuild_collection(collection_name: str | None = None) -> dict:
    _require_skill("ingestion")
    rag = get_rag()
    try:
        result = rag.rebuild_collection_use_case.execute(collection_name)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": result.model_dump(), "trace_id": None}


@router.get("/collections")
def list_collections() -> dict:
    _require_skill("ingestion")
    rag = get_rag()
    result = rag.list_collections_use_case.execute()
    return {"code": 0, "message": "ok",
            "data": [item.model_dump() for item in result], "trace_id": None}


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
def list_documents(collection_name: str | None = None) -> dict:
    _require_skill("document_management")
    rag = get_rag()
    result = rag.list_documents_use_case.execute(collection_name)
    return {"code": 0, "message": "ok",
            "data": [item.model_dump(mode="json") for item in result],
            "trace_id": None}


@router.get("/documents/{document_id}")
def get_document_summary(document_id: str, collection_name: str | None = None) -> dict:
    _require_skill("document_management")
    rag = get_rag()
    try:
        result = rag.get_document_summary_use_case.execute(document_id, collection_name)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": result.model_dump(), "trace_id": None}


@router.get("/documents/{document_id}/detail")
def get_document_detail(document_id: str, collection_name: str | None = None) -> dict:
    _require_skill("document_management")
    rag = get_rag()
    try:
        result = rag.get_document_detail_use_case.execute(document_id, collection_name)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": result.model_dump(mode="json"), "trace_id": None}


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, collection_name: str | None = None) -> dict:
    _require_skill("document_management")
    rag = get_rag()
    try:
        result = rag.delete_document_use_case.execute(document_id, collection_name)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": result.model_dump(), "trace_id": None}


# ── Evaluation ──────────────────────────────────────────────────────────


@router.post("/evaluations/run")
def run_evaluation(request: EvaluationRunRequest) -> dict:
    _require_skill("evaluation")
    rag = get_rag()
    result = rag.run_evaluation_use_case.execute(request)
    return {"code": 0, "message": "ok", "data": result.model_dump(), "trace_id": result.trace_id}


@router.get("/evaluations")
def list_evaluation_reports(limit: int = 20) -> dict:
    _require_skill("evaluation")
    rag = get_rag()
    result = rag.list_evaluation_reports_use_case.execute(limit=limit)
    return {"code": 0, "message": "ok",
            "data": [item.model_dump() for item in result], "trace_id": None}


@router.get("/evaluations/{report_id}")
def get_evaluation_report_detail(report_id: str) -> dict:
    _require_skill("evaluation")
    rag = get_rag()
    try:
        result = rag.get_evaluation_report_detail_use_case.execute(report_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": result.model_dump(), "trace_id": None}


# ── Observability ───────────────────────────────────────────────────────


@router.get("/traces")
def list_traces(trace_type: str | None = None, limit: int = 20) -> dict:
    _require_skill("observability")
    rag = get_rag()
    result = rag.list_traces_use_case.execute(trace_type=trace_type, limit=limit)
    return {"code": 0, "message": "ok",
            "data": [item.model_dump(mode="json") for item in result],
            "trace_id": None}


@router.get("/traces/{trace_id}")
def get_trace_detail(trace_id: str) -> dict:
    _require_skill("observability")
    rag = get_rag()
    try:
        result = rag.get_trace_detail_use_case.execute(trace_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": result.model_dump(mode="json"), "trace_id": None}
