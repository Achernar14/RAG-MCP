"""API Key authentication middleware for REST endpoints.

Authentication is controlled by settings.api_key.enabled:
  - When disabled (default in dev), all requests pass through.
  - When enabled, every request (except /health) must include a valid
    X-API-Key header matching the configured API key.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request


# ── Health endpoint path (always exempt from auth) ──────────────
_HEALTH_PATH = "/api/v1/health"


# ── In-memory cache for settings lookup (avoids container init in dependency) ──
_auth_settings: dict | None = None


def _load_auth_settings() -> dict:
    """Load auth-relevant settings (lazy, cached).

    Returns a dict with keys: enabled, api_key, header_name
    """
    global _auth_settings
    if _auth_settings is not None:
        return _auth_settings

    from rag_mcp.core.settings import load_settings

    settings = load_settings()
    api_key_section = getattr(settings, "api_key", None)
    if api_key_section is None:
        _auth_settings = {"enabled": False, "api_key": "", "header_name": "X-API-Key"}
        return _auth_settings

    api_key = ""
    if api_key_section.api_key_env:
        api_key = os.getenv(api_key_section.api_key_env, "")
    # Support direct key override (takes precedence over env var)
    if getattr(api_key_section, "api_key_direct", None):
        api_key = api_key_section.api_key_direct

    _auth_settings = {
        "enabled": api_key_section.enabled,
        "api_key": api_key,
        "header_name": getattr(api_key_section, "header_name", "X-API-Key"),
    }
    return _auth_settings


async def verify_api_key(request: Request) -> None:
    """FastAPI dependency: validate X-API-Key header when auth is enabled.

    Attach as a router-level dependency or per-route dependency.
    The /health endpoint is always exempt.
    """
    # Always exempt health check
    if request.url.path == _HEALTH_PATH:
        return

    auth = _load_auth_settings()
    if not auth["enabled"]:
        return

    provided = request.headers.get(auth["header_name"])
    if not provided:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include X-API-Key header.",
        )

    if not auth["api_key"]:
        # Key not configured server-side — log once and reject
        raise HTTPException(
            status_code=500,
            detail="Server API key not configured.",
        )

    # Constant-time comparison to mitigate timing attacks
    if not _constant_time_compare(provided, auth["api_key"]):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key.",
        )


def _constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0
