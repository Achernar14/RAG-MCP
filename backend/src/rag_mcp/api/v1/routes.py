"""FastAPI routes for the MVP."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi import HTTPException

from rag_mcp.application.dto.models import (
    EvaluationRunRequest,
    GenerateAnswerRequest,
    IngestRequest,
    QueryRequest,
)
from rag_mcp.core.exceptions import IngestionError, NotFoundError
from rag_mcp.core.container import get_container


router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health() -> dict:
    """Return a basic health response."""
    return {"code": 0, "message": "ok", "data": {"status": "healthy"}, "trace_id": None}


@router.post("/ingest")
def ingest_document(request: IngestRequest) -> dict:
    """Ingest a text or markdown document."""
    try:
        response = get_container().ingest_use_case.execute(request)
    except IngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": response.trace_id}


@router.post("/query")
def query_knowledge(request: QueryRequest) -> dict:
    """Run dense retrieval against the ingested knowledge base."""
    response = get_container().query_use_case.execute(request)
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": response.trace_id}


@router.post("/answers/generate")
def generate_answer(request: GenerateAnswerRequest) -> dict:
    """Generate a grounded answer from retrieved sources."""
    response = get_container().generate_answer_use_case.execute(request)
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": response.trace_id}


@router.get("/documents")
def list_documents() -> dict:
    """List ingested documents."""
    response = get_container().list_documents_use_case.execute()
    payload = [item.model_dump(mode="json") for item in response]
    return {"code": 0, "message": "ok", "data": payload, "trace_id": None}


@router.get("/traces")
def list_traces(trace_type: str | None = None, limit: int = 20) -> dict:
    """List recent traces from local persistence."""
    response = get_container().list_traces_use_case.execute(trace_type=trace_type, limit=limit)
    payload = [item.model_dump(mode="json") for item in response]
    return {"code": 0, "message": "ok", "data": payload, "trace_id": None}


@router.get("/traces/{trace_id}")
def get_trace_detail(trace_id: str) -> dict:
    """Get a single persisted trace."""
    try:
        response = get_container().get_trace_detail_use_case.execute(trace_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": response.model_dump(mode="json"), "trace_id": None}


@router.get("/documents/{document_id}")
def get_document_summary(document_id: str) -> dict:
    """Get a summary view of an ingested document."""
    try:
        response = get_container().get_document_summary_use_case.execute(document_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": None}


@router.get("/documents/{document_id}/detail")
def get_document_detail(document_id: str) -> dict:
    """Get a detailed view of an ingested document."""
    try:
        response = get_container().get_document_detail_use_case.execute(document_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": response.model_dump(mode="json"), "trace_id": None}


@router.delete("/documents/{document_id}")
def delete_document(document_id: str) -> dict:
    """Delete a document and its associated indexes."""
    try:
        response = get_container().delete_document_use_case.execute(document_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": None}


@router.get("/stats")
def get_knowledge_status() -> dict:
    """Return aggregate statistics for the active knowledge base."""
    response = get_container().knowledge_status_use_case.execute()
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": None}


@router.post("/collections/rebuild")
def rebuild_collection(collection_name: str | None = None) -> dict:
    """Rebuild the active collection from current document sources."""
    try:
        response = get_container().rebuild_collection_use_case.execute(collection_name)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": None}


@router.get("/collections")
def list_collections() -> dict:
    """List the currently available logical collection set."""
    response = get_container().list_collections_use_case.execute()
    return {
        "code": 0,
        "message": "ok",
        "data": [item.model_dump() for item in response],
        "trace_id": None,
    }


@router.post("/evaluations/run")
def run_evaluation(request: EvaluationRunRequest) -> dict:
    """Run retrieval evaluation against a golden dataset."""
    response = get_container().run_evaluation_use_case.execute(request)
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": response.trace_id}


@router.get("/evaluations")
def list_evaluation_reports(limit: int = 20) -> dict:
    """List recent evaluation reports."""
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
    try:
        response = get_container().get_evaluation_report_detail_use_case.execute(report_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "message": "ok", "data": response.model_dump(), "trace_id": None}
