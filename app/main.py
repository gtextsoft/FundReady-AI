"""FastAPI application entry point.

Wires middleware and exception handlers and mounts the versioned (`/v1`)
routers. Feature routers are mounted as their endpoints land, starting with
TASKS.md T0.3.

The OpenAPI document is the contract the mobile developer builds against
(DECISIONS.md D1) -- it is served at `/openapi.json` with Swagger UI at `/docs`.
"""

from fastapi import FastAPI

from app import __version__

API_V1_PREFIX = "/v1"

app = FastAPI(
    title="FundReady API",
    version=__version__,
    summary="AI business audit and investor-matching platform for SACI Holdings.",
    description=(
        "REST API for the FundReady platform. All resources live under "
        f"`{API_V1_PREFIX}`. Timestamps are ISO 8601 UTC, currencies are ISO 4217 "
        "codes, and money is expressed in integer minor units. Errors use the "
        "envelope `{\"error\": {\"code\", \"message\", \"details\"}}`."
    ),
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)
