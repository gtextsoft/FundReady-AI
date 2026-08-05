"""FastAPI application entry point.

Wires middleware and exception handlers and mounts the versioned (`/v1`)
routers. Feature routers are mounted as their endpoints land.

The OpenAPI document is the contract the mobile developer builds against
(DECISIONS.md D1) -- it is served at `/openapi.json` with Swagger UI at `/docs`.
"""

import asyncio
import logging
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.core import health
from app.core.config import get_settings
from app.core.db import dispose_engine, get_session_factory
from app.core.errors import register_exception_handlers
from app.core.logging import (
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
    configure_logging,
)
from app.core.monitoring import init_sentry
from app.core.security import CurrentUser, set_user_loader
from app.modules.audit import router as audit_router
from app.modules.brokerage import router as brokerage_router
from app.modules.identity import router as identity_router
from app.modules.identity import service as identity_service
from app.modules.intake import router as intake_router
from app.modules.investor import router as investor_router
from app.modules.readiness import router as readiness_router

API_V1_PREFIX = "/v1"

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    # psycopg's async mode cannot run on Windows' default ProactorEventLoop.
    # This covers anything that starts its own loop from the default policy --
    # the RQ worker, scripts, ad-hoc `asyncio.run`.
    #
    # It does NOT cover uvicorn, which passes an explicit `loop_factory` and so
    # ignores the policy: use `python -m app` (see `app/__main__.py`) or
    # `uvicorn --reload`. A no-op off Windows.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def _load_user(user_id: uuid.UUID) -> CurrentUser | None:
    """Resolve a token subject against the database.

    `core.security` deliberately knows nothing about the identity module -- it
    calls through the `UserLoader` protocol, and this is where the two are
    joined. The composition root is the only place allowed to know both.

    A short-lived session of its own, because authentication happens before the
    request's own session is established.
    """
    async with get_session_factory()() as session:
        return await identity_service.load_current_user(session, user_id)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Configure logging on startup; release pooled connections on shutdown."""
    settings = get_settings()
    # Logging first: `init_sentry` logs whether it started, and that line should
    # be formatted like every other. The worker's `main` orders these the same
    # way for the same reason.
    configure_logging(settings)
    init_sentry(settings, component="api")
    set_user_loader(_load_user)
    logger.info(
        "api starting",
        extra={"context": {"environment": settings.app_env, "version": __version__}},
    )
    yield
    set_user_loader(None)
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
app.include_router(identity_router.router, prefix=API_V1_PREFIX)
app.include_router(intake_router.router, prefix=API_V1_PREFIX)
app.include_router(audit_router.router, prefix=API_V1_PREFIX)
app.include_router(readiness_router.router, prefix=API_V1_PREFIX)
app.include_router(investor_router.router, prefix=API_V1_PREFIX)
app.include_router(brokerage_router.router, prefix=API_V1_PREFIX)
