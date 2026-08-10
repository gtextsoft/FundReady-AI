"""Per-user daily AI token budget (T5.5 / DECISIONS.md D16).

Usage is counted in Redis with a UTC day key. Failures that were billed must
call `record_usage` too — `AiClient` does that on both success and failure.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import Settings, get_settings
from app.core.errors import RateLimitedError

logger = logging.getLogger(__name__)

_connection: Redis | None = None
_connection_url: str | None = None


def _redis(settings: Settings) -> Redis | None:
    global _connection, _connection_url
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


def reset_ai_budget_client() -> None:
    global _connection, _connection_url
    _connection = None
    _connection_url = None


def _day_key(user_id: str, *, now: datetime | None = None) -> str:
    instant = now or datetime.now(UTC)
    return f"ai:budget:{user_id}:{instant.strftime('%Y%m%d')}"


def assert_within_budget(
    user_id: str | None, *, settings: Settings | None = None
) -> None:
    """Refuse a new call when today's spend already meets the cap."""
    if not user_id:
        return
    settings = settings or get_settings()
    budget = settings.ai_daily_budget_tokens_per_user
    if budget is None or budget <= 0:
        return
    client = _redis(settings)
    if client is None:
        return
    try:
        used = int(client.get(_day_key(user_id)) or 0)
    except RedisError:
        logger.warning("ai budget check skipped; redis unavailable")
        return
    if used >= budget:
        raise RateLimitedError(
            "Daily AI budget exceeded. Try again tomorrow.",
            {"reason": "ai_budget_exceeded", "limit": budget, "used": used},
        )


def record_usage(
    user_id: str | None,
    tokens: int,
    *,
    settings: Settings | None = None,
) -> None:
    """Add billed tokens to today's counter (successes and failures)."""
    if not user_id or tokens <= 0:
        return
    settings = settings or get_settings()
    client = _redis(settings)
    if client is None:
        return
    key = _day_key(user_id)
    try:
        count = int(client.incrby(key, tokens))
        if count == tokens:
            # Expire shortly after the UTC day rolls over.
            client.expire(key, 60 * 60 * 36)
    except RedisError:
        logger.warning("ai budget record skipped; redis unavailable")


__all__ = ["assert_within_budget", "record_usage", "reset_ai_budget_client"]
