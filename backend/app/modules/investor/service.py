"""Investor business logic (T4.3).

Layer: **service** (ARCHITECTURE.md section 3) -- business logic and
orchestration. Performs authorization and ownership checks (AUTH.md sections
5-6), calls this module's `repository`, `app.ai`, and other modules' public
service functions only (never their internals). Enqueues background jobs.
Selects the tier serializer for every response carrying report data
(DECISIONS.md D8).

**Discovery is the only place one user reads about another.** Everywhere else
in the platform a caller reads their own rows and `owned_or_404` settles it.
Here an investor reads across tenants by design, so the guard is different in
kind: not "is this yours" but "did this founder agree to be seen, and is what
you are being shown the summary tier". Both live in this file and neither is
optional.
"""

import logging
import uuid
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.caching import uncached_system
from app.ai.client import AiClient, ModelTier
from app.ai.guards import UNTRUSTED_RULE, fence
from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError
from app.core.security import CurrentUser, KycStatus, Role, assert_admin
from app.modules.audit.models import AuditRun
from app.modules.identity import service as identity
from app.modules.identity.models import AuditAction
from app.modules.identity.repository import UserRepository
from app.modules.intake.models import StartupProfile
from app.modules.investor.models import ThesisReviewStatus
from app.modules.investor.repository import (
    DiscoveryRepository,
    InvestorProfileRepository,
    WatchlistRepository,
)
from app.modules.investor.schemas import (
    AnalystChatResponse,
    DiscoveryFilters,
    DiscoveryPage,
    InvestorProfileResponse,
    InvestorProfileUpdate,
    InvestorReviewCard,
    InvestorReviewPage,
    StartupCard,
    WatchlistResponse,
)
from app.modules.mentor.ai_schema import MentorReplyOut
from app.modules.mentor.prompts import MENTOR_SYSTEM_V1

logger = logging.getLogger(__name__)

__all__ = [
    "analyst_chat",
    "decide_thesis",
    "discover",
    "get_or_create_profile",
    "list_theses",
    "list_watchlist",
    "require_investor",
    "require_verified_investor",
    "toggle_watch",
    "update_profile",
    "visible_startup",
]

_NOT_DISCOVERABLE = "No such startup."
"""One message for "no such id" and for "not discoverable".

Same rule as `owned_or_404`: a distinguishable answer turns discovery into an
oracle for whether a given startup id exists on the platform.
"""


def require_investor(actor: CurrentUser) -> None:
    """Discovery is for investors and SACI, never for founders.

    A founder browsing other founders is not a feature anyone asked for, and it
    is the sort of access that gets granted by accident when an endpoint checks
    only that the caller is logged in. Admins are allowed through because they
    have to be able to see what an investor sees when a founder disputes it.
    """
    if actor.role not in (Role.INVESTOR, Role.ADMIN):
        raise ForbiddenError
    if actor.role is Role.ADMIN:
        assert_admin(actor)


async def require_verified_investor(
    session: AsyncSession, actor: CurrentUser
) -> None:
    """T4.1: an investor must have an accepted thesis before dealflow."""
    require_investor(actor)
    if actor.role is Role.ADMIN:
        return
    profile = await InvestorProfileRepository(session).get(actor.id)
    if profile is None or profile.review_status is not ThesisReviewStatus.ACCEPTED:
        raise ForbiddenError(
            "Complete investor verification before browsing dealflow."
        )


async def get_or_create_profile(
    session: AsyncSession, actor: CurrentUser
) -> InvestorProfileResponse:
    require_investor(actor)
    if actor.role is Role.ADMIN:
        raise ForbiddenError("Admins do not hold an investor thesis.")
    row = await InvestorProfileRepository(session).get_or_create(actor.id)
    return InvestorProfileResponse.of(row, actor.kyc_status)


async def update_profile(
    session: AsyncSession, actor: CurrentUser, payload: InvestorProfileUpdate
) -> InvestorProfileResponse:
    require_investor(actor)
    if actor.role is Role.ADMIN:
        raise ForbiddenError("Admins do not hold an investor thesis.")
    row = await InvestorProfileRepository(session).get_or_create(actor.id)
    if row.review_status is ThesisReviewStatus.ACCEPTED:
        raise ForbiddenError("An accepted thesis cannot be edited.")
    data = payload.model_dump()
    for key, value in data.items():
        setattr(row, key, value)
    row.review_status = ThesisReviewStatus.IN_REVIEW
    row.updated_at = datetime.now(UTC)
    await session.flush()
    return InvestorProfileResponse.of(row, actor.kyc_status)


async def list_theses(
    session: AsyncSession,
    actor: CurrentUser,
    *,
    status: ThesisReviewStatus | None,
    limit: int,
    offset: int,
) -> InvestorReviewPage:
    assert_admin(actor)
    rows, total = await InvestorProfileRepository(session).list_for_review(
        status=status, limit=limit, offset=offset
    )
    users = UserRepository(session)
    items: list[InvestorReviewCard] = []
    for row in rows:
        user = await users.get_by_id(row.user_id)
        if user is None:
            continue
        items.append(
            InvestorReviewCard(
                user_id=row.user_id,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                firm=row.firm,
                investor_type=row.investor_type,
                country=row.country,
                linkedin_url=row.linkedin_url,
                thesis_sectors=list(row.thesis_sectors or []),
                thesis_stages=list(row.thesis_stages or []),
                thesis_geographies=list(row.thesis_geographies or []),
                risk_notes=row.risk_notes,
                review_status=row.review_status,
                updated_at=row.updated_at,
            )
        )
    return InvestorReviewPage(items=items, total=total, limit=limit, offset=offset)


async def decide_thesis(
    session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID, *, accept: bool
) -> InvestorReviewCard:
    assert_admin(actor)
    row = await InvestorProfileRepository(session).get(user_id)
    if row is None:
        raise NotFoundError("No such investor thesis.")
    row.review_status = (
        ThesisReviewStatus.ACCEPTED if accept else ThesisReviewStatus.REJECTED
    )
    row.reviewed_at = datetime.now(UTC)
    row.reviewed_by_id = actor.id
    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise NotFoundError("No such investor thesis.")
    user.kyc_status = KycStatus.VERIFIED if accept else KycStatus.FAILED
    await session.flush()
    await identity.record_action(
        session,
        AuditAction.THESIS_REVIEWED,
        actor_id=actor.id,
        target_type="investor_profile",
        target_id=user_id,
        details={"accepted": accept},
    )
    from app.modules.notifications import inbox

    await inbox.notify(
        session,
        user_id,
        kind="thesis_review",
        title="Thesis review decided",
        body="SACI accepted your thesis." if accept else "SACI declined your thesis.",
        payload={"accepted": accept},
    )
    return InvestorReviewCard(
        user_id=row.user_id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        firm=row.firm,
        investor_type=row.investor_type,
        country=row.country,
        linkedin_url=row.linkedin_url,
        thesis_sectors=list(row.thesis_sectors or []),
        thesis_stages=list(row.thesis_stages or []),
        thesis_geographies=list(row.thesis_geographies or []),
        risk_notes=row.risk_notes,
        review_status=row.review_status,
        updated_at=row.updated_at,
    )


async def list_watchlist(
    session: AsyncSession, actor: CurrentUser
) -> WatchlistResponse:
    require_investor(actor)
    ids = await WatchlistRepository(session).list_ids(actor.id)
    return WatchlistResponse(startup_ids=ids)


async def toggle_watch(
    session: AsyncSession, actor: CurrentUser, startup_id: uuid.UUID
) -> WatchlistResponse:
    await require_verified_investor(session, actor)
    await visible_startup(session, actor, startup_id)
    repo = WatchlistRepository(session)
    existing = await repo.get_pair(actor.id, startup_id)
    if existing is None:
        await repo.add(actor.id, startup_id)
        watching = True
    else:
        await repo.remove(existing)
        watching = False
    ids = await repo.list_ids(actor.id)
    return WatchlistResponse(startup_ids=ids, watching=watching)


async def analyst_chat(
    session: AsyncSession,
    actor: CurrentUser,
    startup_id: uuid.UUID,
    message: str,
    history: list[dict[str, str]],
    *,
    client: AiClient | None = None,
) -> AnalystChatResponse:
    """Summary-tier retrieval only — the card, never the stored report."""
    await require_verified_investor(session, actor)
    card = await visible_startup(session, actor, startup_id)
    context = card.model_dump(mode="json")
    user_payload = (
        f"SUMMARY_CARD:\n{context}\n\n"
        f"PRIOR_TURNS:\n{history[-10:]}\n\n"
        f"INVESTOR_QUESTION:\n{message.strip()}\n\n"
        "Answer only from SUMMARY_CARD. If the card does not contain the "
        "figure, say so. Never invent MRR, runway, team, or contact details."
    )
    fenced = fence(user_payload, label="investor_analyst_turn")
    ai = client or AiClient(get_settings())
    result = await ai.complete(
        tier=ModelTier.CHAT,
        prompt=MENTOR_SYSTEM_V1,
        schema=MentorReplyOut,
        system=uncached_system(
            UNTRUSTED_RULE,
            "You are an investor analyst. You may use only the summary card.",
        ),
        messages=[{"role": "user", "content": fenced.text}],
        user_id=str(actor.id),
    )
    out = result.output
    return AnalystChatResponse(
        reply=out.reply,
        citations=[{"kind": c.kind.value, "ref": c.ref} for c in out.citations],
    )


async def discover(
    session: AsyncSession,
    actor: CurrentUser,
    filters: DiscoveryFilters,
    *,
    limit: int,
    offset: int,
) -> DiscoveryPage:
    """One page of discoverable startups, at summary tier."""
    await require_verified_investor(session, actor)

    repository = DiscoveryRepository(session)
    rows = await repository.search(filters, limit=limit, offset=offset)
    total = await repository.count(filters)

    items: list[StartupCard] = []
    for profile, run in rows:
        card = _summary_card(profile, run)
        if card is not None:
            items.append(card)

    return DiscoveryPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


async def visible_startup(
    session: AsyncSession, actor: CurrentUser, startup_id: uuid.UUID
) -> StartupCard:
    """One discoverable startup, or `404`.

    Shared by the card endpoint and by expressing interest, so an investor
    cannot act on a startup that is not discoverable by pasting an id they were
    never shown.
    """
    await require_verified_investor(session, actor)

    row = await DiscoveryRepository(session).visible_run(startup_id)
    if row is None:
        raise NotFoundError(_NOT_DISCOVERABLE)

    profile, run = row
    card = _summary_card(profile, run)
    if card is None:
        raise NotFoundError(_NOT_DISCOVERABLE)
    return card


def _summary_card(profile: StartupProfile, run: AuditRun) -> StartupCard | None:
    """Build a card, or drop a stored report that is not summary-tier shaped.

    A succeeded run with `report = {}` (or missing verdict keys) used to 500
    the whole discovery list. One bad row must not take dealflow down.
    """
    try:
        return StartupCard.of(profile, run)
    except (KeyError, TypeError, ValueError, ValidationError, AttributeError):
        logger.exception(
            "could not serialise discovery card",
            extra={
                "context": {
                    "startup_id": str(profile.id),
                    "run_id": str(run.id),
                }
            },
        )
        return None
