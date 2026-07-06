"""FastAPI routes -- conditionally registered per enabled skill."""

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
from rag_mcp.core.container import get_container
from rag_mcp.core.exceptions import IngestionError, NotFoundError

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])


# -- Health (always available) --


@router.get("/health")
def health() -> dict:
    """Return a basic health response."""
    return {"code": 0, "message": "ok", "data": {"status": "healthy"}, "trace_id": None}


# -- Helper to check skill availability --


def _require_skill(name: str) -> None:
    container = get_container()
    if not container.skill_registry.is_enabled(name):
        raise HTTPException(status_code=404, detail=f"Skill '{name}' is not enabled")


# -- Ingestion skill routes --


@router.post("/ingest")
def ingest_document(request: IngestRequest) -> dict:
    """Ingest a text or markdown document."""
    _require_skill("ingestion")
    try:
        response = get_container().ingest_use_case.execute(request)
    except IngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": response.trace_id}


@router.get("/stats")
def get_knowledge_status(collection_name: str | None = None) -> dict:
    """Return aggregate statistics for the active knowledge base."""
    _require_skill("ingestion")
    response = get_container().knowledge_status_use_case.execute(collection_name)
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": None}


@router.post("/collections/rebuild")
def rebuild_collection(collection_name: str | None = None) -> dict:
    """Rebuild the active collection from current document sources."""
    _require_skill("ingestion")
    try:
        response = get_container().rebuild_collection_use_case.execute(collection_name)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": None}


@router.get("/collections")
def list_collections() -> dict:
    """List the currently available logical collection set."""
    _require_skill("ingestion")
    response = get_container().list_collections_use_case.execute()
    return {
        "code": 0,
        "message": "ok",
        "data": [item.model_dump() for item in response],
        "trace_id": None,
    }


# -- Retrieval skill routes --


@router.post("/query")
def query_knowledge(request: QueryRequest) -> dict:
    """Run dense retrieval against the ingested knowledge base."""
    _require_skill("retrieval")
    response = get_container().query_use_case.execute(request)
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": response.trace_id}


# -- Generation skill routes --


@router.post("/answers/generate")
def generate_answer(request: GenerateAnswerRequest) -> dict:
    """Generate a grounded answer from retrieved sources."""
    _require_skill("generation")
    response = get_container().generate_answer_use_case.execute(request)
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": response.trace_id}


@router.post("/answers/stream")
def stream_answer(request: GenerateAnswerRequest):
    """Stream a grounded answer via Server-Sent Events.

    Returns ``text/event-stream`` with the following event types:

    * ``meta`` — trace metadata (once)
    * ``sources`` — retrieved source items (once)
    * ``token`` — text delta chunks (zero or more)
    * ``done`` — successful completion (once)
    * ``error`` — provider error with fallback (once, on failure)
    """
    _require_skill("generation")

    def _sse_generator():
        for event in get_container().generate_answer_use_case.execute_stream(request):
            event_type = event["event"]
            payload = json.dumps(event["data"], ensure_ascii=False)
            yield f"event: {event_type}\ndata: {payload}\n\n"

    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# -- Document management skill routes --


@router.get("/documents")
def list_documents(collection_name: str | None = None) -> dict:
    """List ingested documents."""
    _require_skill("document_management")
    response = get_container().list_documents_use_case.execute(collection_name)
    payload = [item.model_dump(mode="json") for item in response]
    return {"code": 0, "message": "ok", "data": payload, "trace_id": None}


@router.get("/documents/{document_id}")
def get_document_summary(document_id: str, collection_name: str | None = None) -> dict:
    """Get a summary view of an ingested document."""
    _require_skill("document_management")
    try:
        response = get_container().get_document_summary_use_case.execute(document_id, collection_name)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": None}


@router.get("/documents/{document_id}/detail")
def get_document_detail(document_id: str, collection_name: str | None = None) -> dict:
    """Get a detailed view of an ingested document."""
    _require_skill("document_management")
    try:
        response = get_container().get_document_detail_use_case.execute(document_id, collection_name)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": response.model_dump(mode="json"), "trace_id": None}


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, collection_name: str | None = None) -> dict:
    """Delete a document and its associated indexes."""
    _require_skill("document_management")
    try:
        response = get_container().delete_document_use_case.execute(document_id, collection_name)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": None}


# -- Evaluation skill routes --


@router.post("/evaluations/run")
def run_evaluation(request: EvaluationRunRequest) -> dict:
    """Run retrieval evaluation against a golden dataset."""
    _require_skill("evaluation")
    response = get_container().run_evaluation_use_case.execute(request)
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": response.trace_id}


@router.get("/evaluations")
def list_evaluation_reports(limit: int = 20) -> dict:
    """List recent evaluation reports."""
    _require_skill("evaluation")
    response = get_container().list_evaluation_reports_use_case.execute(limit=limit)
    return {
        "code": 0,
        "message": "ok",
        "data": [item.model_dump() for item in response],
        "trace_id": None,
    }


@router.get("/evaluations/{report_id}")
def get_evaluation_report_detail(report_id: str) -> dict:
    """Get a single evaluation report."""
    _require_skill("evaluation")
    try:
        response = get_container().get_evaluation_report_detail_use_case.execute(report_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": None}


# -- Observability skill routes --


@router.get("/traces")
def list_traces(trace_type: str | None = None, limit: int = 20) -> dict:
    """List recent traces from local persistence."""
    _require_skill("observability")
    response = get_container().list_traces_use_case.execute(trace_type=trace_type, limit=limit)
    payload = [item.model_dump(mode="json") for item in response]
    return {"code": 0, "message": "ok", "data": payload, "trace_id": None}


@router.get("/traces/{trace_id}")
def get_trace_detail(trace_id: str) -> dict:
    """Get a single persisted trace."""
    _require_skill("observability")
    try:
        response = get_container().get_trace_detail_use_case.execute(trace_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": response.model_dump(mode="json"), "trace_id": None}
