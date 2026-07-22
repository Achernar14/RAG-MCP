"""MCP server entrypoint backed by the official SDK.

Usage:
    # stdio (default)
    python -m rag_mcp.mcp.server

    # streamable-http
    python -m rag_mcp.mcp.server --transport streamable-http

    # via pip-installed CLI entry point
    rag-mcp serve --transport streamable-http
"""

from __future__ import annotations

import argparse
import sys

from rag_mcp.mcp.sdk_server import main as _sdk_main


def _parse_args(argv: list[str] | None = None) -> str | None:
    """Parse CLI arguments for transport override."""
    parser = argparse.ArgumentParser(description="RAG MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default=None,
        help="MCP transport protocol (default: reads from settings.yaml)",
    )
    args = parser.parse_args(argv)
    return args.transport


def main(argv: list[str] | None = None) -> int:
    """Entry point for the MCP server (exposed as `rag-mcp serve`)."""
    transport = _parse_args(argv)
    return _sdk_main(transport)


if __name__ == "__main__":
    raise SystemExit(main())
