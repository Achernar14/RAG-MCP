"""Official MCP SDK server wiring -- driven by SkillRegistry.

Supports multiple transports:
  - stdio           : local process communication (default)
  - streamable-http : HTTP-based MCP transport (recommended for remote access)
  - sse             : legacy Server-Sent Events transport
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette

from rag_mcp.core.container import get_container

TransportType = Literal["stdio", "streamable-http", "sse"]


def _build_fastmcp_server() -> FastMCP:
    """Build an official SDK-based MCP server from enabled skills."""
    container = get_container()
    settings = container.settings
    server = FastMCP(name=settings.mcp.server_name)
    server._mcp_server.version = settings.mcp.server_version

    # Collect tools from all enabled skills
    tool_descriptors = container.skill_registry.get_enabled_tools(container)
    for desc in tool_descriptors:
        handler = desc.handler
        handler.__name__ = desc.name
        handler.__doc__ = desc.description
        if desc.return_type is not None:
            handler.__annotations__["return"] = desc.return_type
        server.add_tool(handler, name=desc.name, structured_output=True)

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
