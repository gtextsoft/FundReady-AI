"""Redis-backed request rate limiting (T5.5).

Fail-open when Redis is unavailable so development and unit tests without a
queue still run; production always has `REDIS_URL` (boot validation).
"""

from __future__ import annotations

import logging
from typing import Final

from redis import Redis
from redis.exceptions import RedisError
from starlette.requests import Request

from app.core.config import get_settings
from app.core.errors import RateLimitedError

logger = logging.getLogger(__name__)

# path-prefix → (max requests, window seconds)
AUTH_LIMITS: Final[dict[str, tuple[int, int]]] = {
    "/v1/auth/login": (20, 60),
    "/v1/auth/register": (10, 60),
    "/v1/auth/password-reset": (10, 60),
    "/v1/auth/refresh": (60, 60),
    "/v1/auth/mfa": (30, 60),
    "/v1/auth/verify-email": (30, 60),
}
AI_COSTLY_LIMITS: Final[dict[str, tuple[int, int]]] = {
    "/v1/startups/": (30, 60),  # audits nested under startups
}
DEFAULT_AI_PATH_MARKERS: Final[tuple[str, ...]] = ("/audits", "/evidence/")

_connection: Redis | None = None
_connection_url: str | None = None


def _redis() -> Redis | None:
    global _connection, _connection_url
    settings = get_settings()
    if settings.redis_url is None or not settings.redis_url.get_secret_value().strip():
        return None
    url = settings.redis_url.get_secret_value()
    if _connection is None or _connection_url != url:
        _connection_url = url
        _connection = Redis.from_url(
            url,
            health_check_interval=30,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _connection


def reset_rate_limit_client() -> None:
    """Test helper: drop the cached Redis client."""
    global _connection, _connection_url
    _connection = None
    _connection_url = None


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


def _match_limit(path: str) -> tuple[int, int] | None:
    for prefix, limit in AUTH_LIMITS.items():
        if path.startswith(prefix):
            return limit
    if any(marker in path for marker in DEFAULT_AI_PATH_MARKERS):
        return (30, 60)
    for prefix, limit in AI_COSTLY_LIMITS.items():
        if path.startswith(prefix) and path.rstrip("/").endswith("/publish"):
            return limit
    return None


async def enforce_rate_limit(request: Request) -> None:
    """Raise `RateLimitedError` when the caller exceeds the path budget."""
    limit = _match_limit(request.url.path)
    if limit is None:
        return
    max_requests, window = limit
    client = _redis()
    if client is None:
        return

    bucket = f"rl:{_client_key(request)}:{request.url.path}:{window}"
    try:
        count = int(client.incr(bucket))
        if count == 1:
            client.expire(bucket, window)
    except RedisError:
        logger.warning("rate limit skipped; redis unavailable")
        return

    if count > max_requests:
        raise RateLimitedError(
            details={"retry_after_seconds": window, "limit": max_requests}
        )


__all__ = ["enforce_rate_limit", "reset_rate_limit_client"]
