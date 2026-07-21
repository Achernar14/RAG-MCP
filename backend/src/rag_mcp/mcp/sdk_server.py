"""Official MCP SDK server wiring.

Supports multiple transports:
  - stdio           : local process communication (default)
  - streamable-http : HTTP-based MCP transport (recommended for remote access)
  - sse             : legacy Server-Sent Events transport

MCP tool registration is minimal by design — only read-only knowledge
retrieval and browsing tools are exposed.  See ``mcp/tools.py``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette

from rag_mcp.core.container import get_container
from rag_mcp.mcp.tools import register_mcp_tools

TransportType = Literal["stdio", "streamable-http", "sse"]


def _build_fastmcp_server() -> FastMCP:
    """Build an MCP server with the minimal read-only tool set."""
    container = get_container()
    settings = container.settings
    server = FastMCP(name=settings.mcp.server_name)
    server._mcp_server.version = settings.mcp.server_version

    register_mcp_tools(server, container)

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


def get_sse_app(mount_path: str | None = None) -> Starlette:
    """Return the Starlette ASGI app for MCP SSE transport."""
    return create_fastmcp_server().sse_app(mount_path=mount_path)


def main(transport: TransportType | None = None) -> int:
    """Run the SDK-backed MCP server with the configured transport.

    Args:
        transport: Override transport type. If None, reads from settings.
    """
    server = create_fastmcp_server()
    if transport is None:
        settings = get_container().settings
        transport = settings.mcp.transport  # type: ignore[assignment]

    if transport == "streamable-http":
        server.run(transport="streamable-http")
    elif transport == "sse":
        settings = get_container().settings
        server.run(transport="sse", mount_path=settings.mcp.mount_path)
    else:
        server.run(transport="stdio")

    return 0
