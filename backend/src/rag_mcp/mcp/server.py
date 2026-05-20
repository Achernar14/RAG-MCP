"""MCP stdio entrypoint backed by the official SDK."""

from __future__ import annotations

from rag_mcp.mcp.sdk_server import main


if __name__ == "__main__":
    raise SystemExit(main())
