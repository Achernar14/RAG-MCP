"""Application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI

from rag_mcp.api.v1.routes import router as api_router
from rag_mcp.observability.logging import configure_logging


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    configure_logging()
    app = FastAPI(title="RAG MCP", version="0.1.0")
    app.include_router(api_router)
    return app


app = create_app()
