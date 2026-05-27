"""Synchronous Redis client wrapper."""

from __future__ import annotations

import logging
import os

from rag_mcp.core.settings import RedisSettings

logger = logging.getLogger(__name__)

_REDIS_AVAILABLE: bool | None = None


def _check_redis_available() -> bool:
    """Check whether the redis package is installed."""
    global _REDIS_AVAILABLE
    if _REDIS_AVAILABLE is None:
        try:
            import redis  # noqa: F401
            _REDIS_AVAILABLE = True
        except ImportError:
            _REDIS_AVAILABLE = False
    return _REDIS_AVAILABLE


class RedisClient:
    """Synchronous Redis client wrapper with connection pooling."""

    def __init__(self, settings: RedisSettings) -> None:
        if not _check_redis_available():
            raise ImportError(
                "redis package is not installed. "
                "Install it with: pip install -e ./backend[redis]"
            )
        from redis import Redis
        from redis.connection import ConnectionPool

        password: str | None = None
        if settings.password_env:
            password = os.getenv(settings.password_env) or None

        self._pool = ConnectionPool(
            host=settings.host,
            port=settings.port,
            db=settings.db,
            password=password,
            max_connections=settings.max_connections,
            socket_timeout=settings.socket_timeout,
            socket_connect_timeout=settings.socket_connect_timeout,
        )
        self._client = Redis(connection_pool=self._pool)

    @property
    def client(self):
        """Return the underlying redis.Redis instance."""
        return self._client

    def ping(self) -> bool:
        """Test Redis connectivity. Returns False on any error."""
        try:
            return self._client.ping()
        except Exception:
            return False

    def close(self) -> None:
        """Release connection pool resources."""
        try:
            self._client.close()
        except Exception:
            pass
        try:
            self._pool.disconnect()
        except Exception:
            pass
