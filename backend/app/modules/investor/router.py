"""Investor HTTP endpoints (T4.1, T4.3, T4.4)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import CurrentUserDep, SessionDep, VerifiedInvestor
from app.core.errors import error_responses
from app.modules.intake.fields import Stage
from app.modules.investor import service
from app.modules.investor.schemas import (
    DiscoveryFilters,
    DiscoveryPage,
    IdentitySessionResponse,
    InvestorProfileResponse,
    InvestorProfileUpsert,
    StartupCard,
    WatchlistResponse,
)
from app.modules.mentor.schemas import MentorChatRequest, MentorChatResponse

router = APIRouter(tags=["investor"])

DISCOVERY_NOTE = (
    "\n\n**KYC-verified investors and SACI admins only.** "
    "`403` with `kyc_required` until Stripe Identity verifies the investor.\n\n"
    "Results carry the **summary tier** only."
)


@router.get(
    "/investor/me",
    response_model=InvestorProfileResponse,
    summary="Read investor profile and thesis",
    responses=error_responses(401, 403),
)
async def read_investor_profile(
    actor: CurrentUserDep, session: SessionDep
) -> InvestorProfileResponse:
    return await service.get_profile(session, actor)


@router.put(
    "/investor/me",
    response_model=InvestorProfileResponse,
    summary="Upsert investor thesis and credentials",
    responses=error_responses(401, 403, 422),
)
async def upsert_investor_profile(
    payload: InvestorProfileUpsert, actor: CurrentUserDep, session: SessionDep
) -> InvestorProfileResponse:
    return await service.upsert_profile(session, actor, payload)


@router.post(
    "/investor/kyc/session",
    response_model=IdentitySessionResponse,
    summary="Start Stripe Identity verification",
    responses=error_responses(401, 403, 422, 500),
)
async def start_kyc(
    actor: CurrentUserDep, session: SessionDep
) -> IdentitySessionResponse:
    return await service.start_identity_session(session, actor)


@router.get(
    "/discover",
    response_model=DiscoveryPage,
    summary="Browse discoverable startups",
    description="Ranked against the caller's thesis when one is set." + DISCOVERY_NOTE,
    responses=error_responses(401, 403, 422),
)
async def discover(
    actor: VerifiedInvestor,
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
    description=DISCOVERY_NOTE,
    responses=error_responses(401, 403, 404, 422),
)
async def read_startup_card(
    startup_id: uuid.UUID, actor: VerifiedInvestor, session: SessionDep
) -> StartupCard:
    return await service.visible_startup(session, actor, startup_id)


@router.post(
    "/discover/{startup_id}/analyst/chat",
    response_model=MentorChatResponse,
    summary="Investor AI analyst chat (summary tier only)",
    description=(
        "Answers from **summary-tier** retrieval only. Full-report fields are "
        "never loaded into context, even if the prompt asks for them."
        + DISCOVERY_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def analyst_chat(
    startup_id: uuid.UUID,
    payload: MentorChatRequest,
    actor: VerifiedInvestor,
    session: SessionDep,
) -> MentorChatResponse:
    return await service.analyst_chat(
        session,
        actor,
        startup_id,
        message=payload.message,
        history=payload.history,
    )


@router.get(
    "/watchlist",
    response_model=WatchlistResponse,
    summary="Synced investor watchlist",
    responses=error_responses(401, 403),
)
async def get_watchlist(
    actor: VerifiedInvestor, session: SessionDep
) -> WatchlistResponse:
    return await service.watchlist(session, actor)


@router.post(
    "/watchlist/{startup_id}",
    response_model=WatchlistResponse,
    summary="Toggle a startup on the watchlist",
    responses=error_responses(401, 403, 404),
)
async def toggle_watchlist(
    startup_id: uuid.UUID, actor: VerifiedInvestor, session: SessionDep
) -> WatchlistResponse:
    return await service.toggle_watch(session, actor, startup_id)
