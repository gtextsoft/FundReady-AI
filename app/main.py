"""FastAPI application entry point.

Wires middleware and exception handlers and mounts the versioned (`/v1`)
routers. Feature routers are mounted as their endpoints land.

The OpenAPI document is the contract the mobile developer builds against
(DECISIONS.md D1) -- it is served at `/openapi.json` with Swagger UI at `/docs`.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.core import health
from app.core.config import get_settings
from app.core.db import dispose_engine
from app.core.errors import register_exception_handlers
from app.core.logging import (
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
    configure_logging,
)

API_V1_PREFIX = "/v1"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Configure logging on startup; release pooled connections on shutdown."""
    settings = get_settings()
    configure_logging(settings)
    logger.info(
        "api starting",
        extra={"context": {"environment": settings.app_env, "version": __version__}},
    )
    yield
    await dispose_engine()


app = FastAPI(
    title="FundReady API",
    version=__version__,
    summary="AI business audit and investor-matching platform for SACI Holdings.",
    description=(
        "REST API for the FundReady platform. All resources live under "
        f"`{API_V1_PREFIX}`. Timestamps are ISO 8601 UTC, currencies are ISO 4217 "
        "codes, and money is expressed in integer minor units.\n\n"
        "Every error response uses the envelope "
        '`{"error": {"code", "message", "details"}}`. Branch on `code`, which is '
        "stable; never parse `message`.\n\n"
        f"Every response carries an `{REQUEST_ID_HEADER}` header. Quote it in a "
        "support report and we can find the exact log line."
    ),
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

_settings = get_settings()

# Restricted to configured origins; empty configuration means no cross-origin
# access at all, which is the correct default for a mobile-only client
# (AUTH.md section 13).
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)
app.add_middleware(RequestContextMiddleware)

register_exception_handlers(app)

app.include_router(health.router, prefix=API_V1_PREFIX)
