"""Liveness endpoint.

Deliberately shallow. This is what a load balancer polls, so it must not touch
the database, Redis, or any external service: a transient Supabase blip should
not read as "this process is dead" and get the platform restarted. It is also
unauthenticated, so it reveals nothing beyond the deployed version.

A deeper *readiness* check that probes dependencies is a separate, authenticated
endpoint -- deferred to T5.5 rather than conflated with liveness here.
"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import __version__
from app.core.config import Environment, get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Service liveness."""

    status: Literal["ok"] = Field(description="Always `ok` when the API is serving.")
    version: str = Field(description="Deployed API version.", examples=["0.1.0"])
    environment: Environment = Field(description="Deployment environment.")


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
