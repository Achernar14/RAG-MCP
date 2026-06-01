"""MCP server entrypoint backed by the official SDK.

Usage:
    # stdio (default)
    python -m rag_mcp.mcp.server

    # streamable-http
    python -m rag_mcp.mcp.server --transport streamable-http

    # sse
    python -m rag_mcp.mcp.server --transport sse
"""

from __future__ import annotations

import argparse

from rag_mcp.mcp.sdk_server import main


def _parse_args() -> str | None:
    """Parse CLI arguments for transport override."""
    parser = argparse.ArgumentParser(description="RAG MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default=None,
        help="MCP transport protocol (default: reads from settings.yaml)",
    )
    args = parser.parse_args()
    return args.transport


if __name__ == "__main__":
    transport = _parse_args()
    raise SystemExit(main(transport))
