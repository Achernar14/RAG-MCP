"""Official MCP SDK server wiring.

Supports two transports:
  - stdio           : local process communication (default)
  - streamable-http : HTTP-based MCP transport (recommended for remote access)

MCP tool registration is minimal by design — only read-only knowledge
retrieval and browsing tools are exposed.  See ``mcp/tools.py``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette

from rag_mcp.factory import get_rag
from rag_mcp.mcp.tools import register_mcp_tools

TransportType = Literal["stdio", "streamable-http"]


def _build_fastmcp_server() -> FastMCP:
    """Build an MCP server with the minimal read-only tool set."""
    rag = get_rag()
    settings = rag.settings
    server = FastMCP(name=settings.mcp.server_name)
    server._mcp_server.version = settings.mcp.server_version

    register_mcp_tools(server, rag)

    return server


@lru_cache(maxsize=1)
def create_fastmcp_server() -> FastMCP:
    """Return the shared official SDK-based MCP server instance."""
    return _build_fastmcp_server()


def reset_fastmcp_server() -> None:
    """Clear the cached SDK server instance."""
    create_fastmcp_server.cache_clear()


def get_streamable_http_app() -> Starlette:
    """Return the Starlette ASGI app for MCP Streamable HTTP transport."""
    return create_fastmcp_server().streamable_http_app()


def main(transport: TransportType | None = None) -> int:
    """Run the SDK-backed MCP server with the configured transport.

    Args:
        transport: Override transport type. If None, reads from settings.
    """
    server = create_fastmcp_server()
    if transport is None:
        settings = get_rag().settings
        transport = settings.mcp.transport  # type: ignore[assignment]

    if transport == "streamable-http":
        server.run(transport="streamable-http")
    else:
        server.run(transport="stdio")

    return 0
