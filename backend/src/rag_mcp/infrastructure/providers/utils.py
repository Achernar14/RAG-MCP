"""Shared helpers for external provider integrations."""

from __future__ import annotations

import os

from rag_mcp.core.exceptions import ConfigurationError


def require_env_value(env_name: str | None, *, provider_name: str) -> str:
    """Resolve a required API key from an environment variable."""
    if not env_name:
        raise ConfigurationError(f"{provider_name} api_key_env is not configured")
    value = os.getenv(env_name)
    if not value:
        raise ConfigurationError(
            f"{provider_name} API key environment variable is missing: {env_name}"
        )
    return value
