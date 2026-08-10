"""Investor HTTP endpoints (T4.3).

Investor profiles, thesis, discovery/ranking, and the investor AI analyst chat.

Layer: **router** (ARCHITECTURE.md section 3) -- HTTP only. Validate the request
with `schemas`, call exactly one `service` method, return a response schema.
No business logic, no database access, no LLM calls.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import CurrentUserDep, SessionDep
from app.core.errors import error_responses
from app.modules.intake.fields import Stage
from app.modules.investor import service
from app.modules.investor.schemas import DiscoveryFilters, DiscoveryPage, StartupCard

router = APIRouter(tags=["investor"])

DISCOVERY_NOTE = (
    "\n\n**Investors and SACI admins only; `403` for a founder.**\n\n"
    "Every startup here opted in explicitly — running an audit does not make a "
    "founder discoverable, publishing does. Results carry the **summary tier** "
    "only: the two verdicts and the four discovery columns. There is no "
    "founder name, no contact detail, and none of the submitted figures. That "
    "is the brokerage: the verdict is enough to decide whether to ask for an "
    "introduction, and not enough to skip one."
)


@router.get(
    "/discover",
    response_model=DiscoveryPage,
    summary="Browse discoverable startups",
    description=(
        "Startups that have published themselves, newest first.\n\n"
        "Filters are the four indexed columns. `sector` matches "
        "case-insensitively because sector is free text — a founder who typed "
        "`Fintech` and a filter of `fintech` mean the same thing.\n\n"
        "`total` is the count ignoring pagination, so a client can render "
        '"page N of M".\n\n'
        "A startup appears only once it has a **succeeded** audit. A published "
        "profile with no verdict is not listed: a card with nothing on it "
        "invites a direct approach, which is what the brokerage prevents."
        + DISCOVERY_NOTE
    ),
    responses=error_responses(401, 403, 422),
)
async def discover(
    actor: CurrentUserDep,
    session: SessionDep,
    sector: Annotated[str | None, Query(max_length=120)] = None,
    stage: Annotated[Stage | None, Query()] = None,
    country: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DiscoveryPage:
    return await service.discover(
        session,
        actor,
        DiscoveryFilters(sector=sector, stage=stage, country=country),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/discover/{startup_id}",
    response_model=StartupCard,
    summary="Read one discoverable startup",
    description=(
        "The same card the list returns.\n\n"
        "**`404` for a startup that has not published**, exactly as for one "
        "that does not exist — a distinguishable answer would turn this into "
        "an oracle for which startup ids are real." + DISCOVERY_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def read_startup_card(
    startup_id: uuid.UUID, actor: CurrentUserDep, session: SessionDep
) -> StartupCard:
    return await service.visible_startup(session, actor, startup_id)
