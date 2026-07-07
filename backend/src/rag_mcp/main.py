"""Application entrypoint.

Creates a FastAPI application that serves both:
  - REST API at /api/v1/*  (existing endpoints)
  - MCP Streamable HTTP at /mcp  (MCP protocol over HTTP)

The MCP HTTP transport is mounted when the configured transport is
'streamable-http' or 'sse'.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from rag_mcp.api.v1.routes import router as api_router
from rag_mcp.core.container import get_container
from rag_mcp.core.exceptions import CollectionNameError
from rag_mcp.observability.logging import configure_logging


def create_app() -> FastAPI:
    """Create the FastAPI application with optional MCP HTTP transport."""
    configure_logging()
    container = get_container()
    settings = container.settings

    app = FastAPI(title="RAG MCP", version="0.1.0")

    # CORS middleware — allows browser-based Dashboard to access the REST API
    if settings.cors.enabled:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors.allow_origins,
            allow_methods=settings.cors.allow_methods,
            allow_headers=settings.cors.allow_headers,
            allow_credentials=settings.cors.allow_credentials,
        )

    # Global exception handler: convert CollectionNameError → HTTP 400
    @app.exception_handler(CollectionNameError)
    async def _handle_collection_name_error(
        request: Request, exc: CollectionNameError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "code": 400,
                "message": str(exc),
                "data": None,
                "trace_id": None,
            },
        )

    app.include_router(api_router)

    # Mount MCP HTTP transport if configured
    transport = settings.mcp.transport
    if transport in ("streamable-http", "sse"):
        _mount_mcp_transport(app, transport, settings.mcp.mount_path)

    return app


def _mount_mcp_transport(app: FastAPI, transport: str, mount_path: str) -> None:
    """Mount the MCP ASGI sub-app on the FastAPI application."""
    if transport == "streamable-http":
        from rag_mcp.mcp.sdk_server import get_streamable_http_app

        mcp_app = get_streamable_http_app()
    elif transport == "sse":
        from rag_mcp.mcp.sdk_server import get_sse_app

        mcp_app = get_sse_app(mount_path=mount_path)
    else:
        return

    app.mount(mount_path, mcp_app)


app = create_app()
