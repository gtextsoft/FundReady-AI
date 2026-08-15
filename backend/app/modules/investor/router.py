"""Investor HTTP endpoints (T4.1, T4.3, T4.4)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import CurrentAdmin, CurrentUserDep, SessionDep
from app.core.errors import error_responses
from app.modules.intake.fields import Stage
from app.modules.investor import service
from app.modules.investor.models import ThesisReviewStatus
from app.modules.investor.schemas import (
    AnalystChatRequest,
    AnalystChatResponse,
    DiscoveryFilters,
    DiscoveryPage,
    InvestorProfileResponse,
    InvestorProfileUpdate,
    InvestorReviewCard,
    InvestorReviewPage,
    StartupCard,
    ThesisDecision,
    WatchlistResponse,
)

router = APIRouter(tags=["investor"])

DISCOVERY_NOTE = (
    "\n\n**Investors and SACI admins only; `403` for a founder.**\n\n"
    "Investors must have an **accepted thesis** (T4.1) before this list "
    "returns rows. Admins need MFA.\n\n"
    "Every startup here opted in explicitly. Results carry the **summary tier** "
    "only: the two verdicts and the four discovery columns."
)


@router.get(
    "/investor/me",
    response_model=InvestorProfileResponse,
    summary="Read your investor thesis",
    description="Creates an empty thesis row on first read. Investors only.",
    responses=error_responses(401, 403),
)
async def read_investor_me(
    actor: CurrentUserDep, session: SessionDep
) -> InvestorProfileResponse:
    return await service.get_or_create_profile(session, actor)


@router.put(
    "/investor/me",
    response_model=InvestorProfileResponse,
    summary="Submit your investor thesis for review",
    description=(
        "Writes thesis fields and sets `review_status` to `in_review`. "
        "An accepted thesis cannot be edited."
    ),
    responses=error_responses(401, 403, 422),
)
async def write_investor_me(
    payload: InvestorProfileUpdate, actor: CurrentUserDep, session: SessionDep
) -> InvestorProfileResponse:
    return await service.update_profile(session, actor, payload)


@router.get(
    "/admin/investors",
    response_model=InvestorReviewPage,
    summary="List investor theses for review",
    description="**SACI admins with MFA only.** Filter with `review_status`.",
    responses=error_responses(401, 403, 422),
)
async def list_investor_theses(
    actor: CurrentAdmin,
    session: SessionDep,
    review_status: Annotated[ThesisReviewStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InvestorReviewPage:
    return await service.list_theses(
        session, actor, status=review_status, limit=limit, offset=offset
    )


@router.post(
    "/admin/investors/{user_id}/thesis-review",
    response_model=InvestorReviewCard,
    summary="Accept or reject an investor thesis",
    description="**SACI admins with MFA only.** Acceptance sets `kyc_status=verified`.",
    responses=error_responses(401, 403, 404, 422),
)
async def decide_thesis(
    user_id: uuid.UUID,
    payload: ThesisDecision,
    actor: CurrentAdmin,
    session: SessionDep,
) -> InvestorReviewCard:
    return await service.decide_thesis(session, actor, user_id, accept=payload.accept)


@router.get(
    "/watchlist",
    response_model=WatchlistResponse,
    summary="Your watched startups",
    description="Startup ids this investor starred. Empty until any are starred.",
    responses=error_responses(401, 403),
)
async def read_watchlist(
    actor: CurrentUserDep, session: SessionDep
) -> WatchlistResponse:
    return await service.list_watchlist(session, actor)


@router.post(
    "/watchlist/{startup_id}",
    response_model=WatchlistResponse,
    summary="Toggle a startup on your watchlist",
    description="Adds if absent, removes if present. Startup must be discoverable.",
    responses=error_responses(401, 403, 404, 422),
)
async def toggle_watch(
    startup_id: uuid.UUID, actor: CurrentUserDep, session: SessionDep
) -> WatchlistResponse:
    return await service.toggle_watch(session, actor, startup_id)


@router.get(
    "/discover",
    response_model=DiscoveryPage,
    summary="Browse discoverable startups",
    description=(
        "Startups that have published themselves, newest first.\n\n"
        "Filters are the four indexed columns. `total` is the count ignoring "
        "pagination." + DISCOVERY_NOTE
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
    description="The same card the list returns. `404` if not published."
    + DISCOVERY_NOTE,
    responses=error_responses(401, 403, 404, 422),
)
async def read_startup_card(
    startup_id: uuid.UUID, actor: CurrentUserDep, session: SessionDep
) -> StartupCard:
    return await service.visible_startup(session, actor, startup_id)


@router.post(
    "/discover/{startup_id}/analyst/chat",
    response_model=AnalystChatResponse,
    summary="Ask the AI analyst about a summary card",
    description=(
        "Retrieval is **summary-tier only**. The model is given the discovery "
        "card and nothing from the stored full report, even if the prompt asks."
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def analyst_chat(
    startup_id: uuid.UUID,
    payload: AnalystChatRequest,
    actor: CurrentUserDep,
    session: SessionDep,
) -> AnalystChatResponse:
    return await service.analyst_chat(
        session,
        actor,
        startup_id,
        message=payload.message,
        history=payload.history,
    )
