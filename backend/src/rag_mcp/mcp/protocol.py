"""Compatibility MCP protocol adapter (TRANSITIONAL — prefer sdk_server.py).

The canonical MCP server wiring lives in ``sdk_server.py`` (FastMCP-based).
This module is a **compatibility shim** that wraps the SDK server for:

1. Legacy local messages shaped like ``{"tool": "...", "arguments": {...}}``
2. Synchronous JSON-RPC adapter tests that still call ``handle_message(...)``
3. Line-delimited stdio loop (``run_stdio_loop``) for pre-SDK clients

**Relationship to sdk_server.py**: All tool discovery and execution is
delegated to ``create_fastmcp_server()`` from ``sdk_server.py`` — this module
only handles wire-format translation (JSON-RPC envelopes, legacy payloads).
There is no duplication; the two modules operate at different layers:

* ``sdk_server.py`` — MCP server instance + tool registration (application layer)
* ``protocol.py``   — wire-format adapters + legacy compat (presentation layer)

New code should use ``sdk_server.py`` directly.  This module will be removed
in a future major version once all callers have migrated.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from mcp.server.fastmcp.exceptions import ToolError

from rag_mcp.factory import get_container
from rag_mcp.core.exceptions import NotFoundError, RagMcpError
from rag_mcp.mcp.sdk_server import create_fastmcp_server


JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2025-06-18"


class LegacyToolError(Exception):
    """Raised for compatibility-mode protocol failures."""


def _ok(data: Any) -> dict[str, Any]:
    """Build a successful legacy MCP payload."""
    return {"ok": True, "data": data}


def _error(message: str) -> dict[str, Any]:
    """Build an error legacy MCP payload."""
    return {"ok": False, "error": message}


def _jsonrpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    """Build a JSON-RPC result payload."""
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def _jsonrpc_error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    """Build a JSON-RPC error payload."""
    payload: dict[str, Any] = {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }
    if data is not None:
        payload["error"]["data"] = data
    return payload


def _serialize(value: Any) -> Any:
    """Convert SDK and DTO payloads to plain JSON-serializable data."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, tuple):
        return tuple(_serialize(item) for item in value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


def _normalize_structured_result(result: Any) -> Any:
    """Unwrap SDK list results to preserve existing protocol response shapes."""
    if isinstance(result, dict) and set(result.keys()) == {"result"}:
        return result["result"]
    return result


def _list_sdk_tools() -> list[dict[str, Any]]:
    """Return tool definitions from the official SDK server."""
    tools = asyncio.run(create_fastmcp_server().list_tools())
    return [_serialize(tool) for tool in tools]


def _execute_sdk_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], Any]:
    """Execute a tool through the official SDK server and normalize its result."""
    arguments = arguments or {}
    result = asyncio.run(
        create_fastmcp_server().call_tool(tool_name, arguments)
    )
    # With structured_output=False, call_tool returns list[TextContent].
    # Parse the text content as JSON for structured result.
    content_blocks = _serialize(result)
    structured_result = None
    if isinstance(result, list) and result:
        try:
            import json
            structured_result = json.loads(result[0].text)
        except (json.JSONDecodeError, AttributeError, IndexError):
            pass
    return content_blocks, _normalize_structured_result(_serialize(structured_result))


def _handle_legacy_tool_message(message: dict[str, Any]) -> dict[str, Any]:
    """Handle backward-compatible local tool messages."""
    tool = message.get("tool")
    arguments = message.get("arguments", {})
    if not tool:
        return _error("Missing required field: tool")
    try:
        _, structured_result = _execute_sdk_tool(tool, arguments)
    except (ToolError, LegacyToolError, NotFoundError, RagMcpError) as exc:
        return _error(str(exc))
    return _ok(structured_result)


def _handle_initialize(params: dict[str, Any]) -> dict[str, Any]:
    """Handle MCP initialize."""
    client_protocol_version = params.get("protocolVersion")
    selected_protocol_version = client_protocol_version or MCP_PROTOCOL_VERSION
    settings = get_container().settings
    return {
        "protocolVersion": selected_protocol_version,
        "capabilities": {
            "tools": {},
        },
        "serverInfo": {
            "name": settings.mcp.server_name,
            "version": settings.mcp.server_version,
        },
    }


def _handle_tools_list(params: dict[str, Any]) -> dict[str, Any]:
    """Return SDK-backed MCP tool definitions."""
    del params
    return {"tools": _list_sdk_tools()}


def _handle_tools_call(params: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool via the SDK-backed MCP standard method."""
    name = params.get("name")
    arguments = params.get("arguments", {}) or {}
    if not name:
        raise LegacyToolError("Missing required parameter: name")
    content_blocks, structured_result = _execute_sdk_tool(name, arguments)
    return {
        "content": content_blocks,
        "structuredContent": structured_result,
        "isError": False,
    }


def _handle_jsonrpc_message(message: dict[str, Any]) -> dict[str, Any] | None:
    """Handle MCP JSON-RPC requests through the SDK-backed tool layer."""
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params", {}) or {}

    if method == "notifications/initialized":
        return None

    try:
        if method == "initialize":
            return _jsonrpc_result(request_id, _handle_initialize(params))
        if method == "tools/list":
            return _jsonrpc_result(request_id, _handle_tools_list(params))
        if method == "tools/call":
            return _jsonrpc_result(request_id, _handle_tools_call(params))
        return _jsonrpc_error(request_id, -32601, f"Method not found: {method}")
    except (ToolError, LegacyToolError, NotFoundError, RagMcpError) as exc:
        if method == "tools/call":
            return _jsonrpc_result(
                request_id,
                {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            )
        return _jsonrpc_error(request_id, -32000, str(exc))
    except Exception as exc:  # pragma: no cover - defensive layer
        return _jsonrpc_error(request_id, -32603, "Internal error", str(exc))


def handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    """Handle either legacy tool payloads or MCP JSON-RPC messages."""
    if "tool" in message:
        return _handle_legacy_tool_message(message)
    if message.get("jsonrpc") == JSONRPC_VERSION and "method" in message:
        return _handle_jsonrpc_message(message)
    return _error("Unsupported message format")


def run_stdio_loop() -> int:
    """Legacy compatibility loop for line-delimited local JSON messages."""
    for line in sys.stdin:
        payload = line.strip()
        if not payload:
            continue
        try:
            message = json.loads(payload)
            result = handle_message(message)
            if result is None:
                continue
        except Exception as exc:  # pragma: no cover - integration behavior
            result = {"ok": False, "error": str(exc)}
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0
