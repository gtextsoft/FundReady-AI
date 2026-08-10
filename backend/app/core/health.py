"""Liveness and readiness endpoints.

Liveness is deliberately shallow (load balancers). Readiness probes Postgres
and Redis so orchestration can stop routing when dependencies are down (T5.5).
"""

from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from app import __version__
from app.core.config import Environment, get_settings
from app.core.db import get_session_factory

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Service liveness."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"status": "ok", "version": "0.1.0", "environment": "production"}
            ]
        }
    )

    status: Literal["ok"] = Field(description="Always `ok` when the API is serving.")
    version: str = Field(description="Deployed API version.", examples=["0.1.0"])
    environment: Environment = Field(description="Deployment environment.")


class ReadinessResponse(BaseModel):
    """Dependency readiness."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ready",
                    "version": "0.1.0",
                    "database": True,
                    "redis": True,
                }
            ]
        }
    )

    status: Literal["ready", "not_ready"]
    version: str
    database: bool
    redis: bool


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check",
    description=(
        "Returns 200 whenever the API process is serving requests. "
        "Requires no authentication and performs no dependency checks, so a "
        "200 means *this process is alive*, not *the platform is healthy*."
    ),
    responses={200: {"description": "The API is serving requests."}},
)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=__version__,
        environment=settings.app_env,
    )


async def _database_ok() -> bool:
    try:
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _redis_ok() -> bool:
    settings = get_settings()
    if settings.redis_url is None or not settings.redis_url.get_secret_value().strip():
        return False
    try:
        from redis import Redis

        client = Redis.from_url(
            settings.redis_url.get_secret_value(),
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        return bool(client.ping())
    except Exception:
        return False


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness check",
    description=(
        "Probes Postgres and Redis. Returns HTTP `503` with this same body when "
        "either is unreachable so a load balancer can drain traffic. "
        "Unauthenticated on purpose — the response only names dependency "
        "health, never secrets or data. Branch on `status` / the status code."
    ),
    responses={200: {"description": "Dependencies are reachable."}},
)
async def ready(response: Response) -> ReadinessResponse:
    database = await _database_ok()
    redis = _redis_ok()
    ok = database and redis
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if ok else "not_ready",
        version=__version__,
        database=database,
        redis=redis,
    )
