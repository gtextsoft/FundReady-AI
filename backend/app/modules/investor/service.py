"""Investor business logic (T4.1, T4.3, T4.4).

Discovery is the only place one user reads about another. KYC is enforced here
and in `core.deps.require_kyc_verified` (AUTH.md §8).
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.caching import uncached_system
from app.ai.client import AiClient, ModelTier
from app.ai.guards import UNTRUSTED_RULE, fence
from app.core.config import Settings, get_settings
from app.core.errors import (
    ConfigurationError,
    ForbiddenError,
    InvalidRequestError,
    NotFoundError,
)
from app.core.security import CurrentUser, KycStatus, Role, assert_admin
from app.modules.audit.reports import summary_report
from app.modules.audit.repository import AuditRunRepository
from app.modules.audit.runs import AuditStatus
from app.modules.identity.models import AuditAction
from app.modules.identity.repository import UserRepository
from app.modules.identity.service import record_action
from app.modules.investor.models import InvestorProfile
from app.modules.investor.prompts import ANALYST_SYSTEM_V1
from app.modules.investor.repository import (
    DiscoveryRepository,
    InvestorProfileRepository,
    WatchlistRepository,
)
from app.modules.investor.schemas import (
    DiscoveryFilters,
    DiscoveryPage,
    IdentitySessionResponse,
    InvestorProfileResponse,
    InvestorProfileUpsert,
    StartupCard,
    WatchlistResponse,
)
from app.modules.mentor.ai_schema import MentorReplyOut
from app.modules.mentor.schemas import (
    ChatTurn,
    CitationKind,
    MentorChatResponse,
    MentorCitation,
)

logger = logging.getLogger(__name__)

__all__ = [
    "analyst_chat",
    "apply_identity_webhook_event",
    "discover",
    "get_profile",
    "require_investor",
    "require_kyc",
    "start_identity_session",
    "toggle_watch",
    "upsert_profile",
    "visible_startup",
    "watchlist",
]

_NOT_DISCOVERABLE = "No such startup."


def require_investor(actor: CurrentUser) -> None:
    if actor.role is Role.ADMIN:
        assert_admin(actor)
        return
    if actor.role is not Role.INVESTOR:
        raise ForbiddenError


def require_kyc(actor: CurrentUser) -> None:
    """Investors must be Stripe-Identity verified; admins pass with MFA."""
    if actor.role is Role.ADMIN:
        assert_admin(actor)
        return
    if actor.role is not Role.INVESTOR:
        raise ForbiddenError
    if actor.kyc_status is not KycStatus.VERIFIED:
        raise ForbiddenError(
            "Complete investor identity verification to continue.",
            {"reason": "kyc_required", "kyc_status": actor.kyc_status.value},
        )


def _rank_score(card: StartupCard, thesis: InvestorProfile | None) -> int:
    """Higher is a better thesis fit. Pure keyword matching — no embeddings."""
    if thesis is None:
        return 0
    score = 0
    sectors = {s.lower() for s in (thesis.thesis_sectors or []) if isinstance(s, str)}
    stages = {str(s).lower() for s in (thesis.thesis_stages or [])}
    geos = {g.upper() for g in (thesis.thesis_geographies or []) if isinstance(g, str)}
    if card.sector and card.sector.lower() in sectors:
        score += 3
    if card.stage is not None and card.stage.value.lower() in stages:
        score += 2
    if card.country and card.country.upper() in geos:
        score += 2
    if card.fundability.score is not None:
        score += min(card.fundability.score // 25, 3)
    return score


async def discover(
    session: AsyncSession,
    actor: CurrentUser,
    filters: DiscoveryFilters,
    *,
    limit: int,
    offset: int,
) -> DiscoveryPage:
    """One page of discoverable startups, ranked against the investor thesis."""
    require_investor(actor)
    require_kyc(actor)

    repository = DiscoveryRepository(session)
    # Fetch a wider window then rank — thesis sort is in-process.
    fetch_limit = min(max(limit + offset, limit * 3), 200)
    rows = await repository.search(filters, limit=fetch_limit, offset=0)
    total = await repository.count(filters)

    thesis = await InvestorProfileRepository(session).get_by_user(actor.id)
    cards = [StartupCard.of(profile, run) for profile, run in rows]
    cards.sort(
        key=lambda c: (-_rank_score(c, thesis), c.published_at or c.startup_id.hex),
        reverse=False,
    )
    # After sort by (-score, published), reverse=False keeps highest score first
    # when using negative score. published_at as secondary: newer first needs
    # careful ordering — use stable: score desc then published desc.
    cards.sort(
        key=lambda c: (
            -_rank_score(c, thesis),
            -(c.published_at.timestamp() if c.published_at else 0),
        )
    )
    page = cards[offset : offset + limit]
    return DiscoveryPage(items=page, total=total, limit=limit, offset=offset)


async def visible_startup(
    session: AsyncSession, actor: CurrentUser, startup_id: uuid.UUID
) -> StartupCard:
    require_investor(actor)
    require_kyc(actor)

    row = await DiscoveryRepository(session).visible_run(startup_id)
    if row is None:
        raise NotFoundError(_NOT_DISCOVERABLE)
    profile, run = row
    return StartupCard.of(profile, run)


def _profile_response(
    profile: InvestorProfile | None, kyc_status: KycStatus
) -> InvestorProfileResponse:
    if profile is None:
        return InvestorProfileResponse(kyc_status=kyc_status.value)
    return InvestorProfileResponse(
        firm=profile.firm,
        investor_type=profile.investor_type,
        country=profile.country,
        linkedin_url=profile.linkedin_url,
        thesis_sectors=[str(s) for s in (profile.thesis_sectors or [])],
        thesis_stages=[str(s) for s in (profile.thesis_stages or [])],
        thesis_geographies=[str(g) for g in (profile.thesis_geographies or [])],
        ticket_min_minor=profile.ticket_min_minor,
        ticket_max_minor=profile.ticket_max_minor,
        ticket_currency=profile.ticket_currency,
        risk_notes=profile.risk_notes,
        kyc_status=kyc_status.value,
    )


async def get_profile(
    session: AsyncSession, actor: CurrentUser
) -> InvestorProfileResponse:
    require_investor(actor)
    profile = await InvestorProfileRepository(session).get_by_user(actor.id)
    user = await UserRepository(session).get_by_id(actor.id)
    status = user.kyc_status if user is not None else actor.kyc_status
    return _profile_response(profile, status)


async def upsert_profile(
    session: AsyncSession, actor: CurrentUser, payload: InvestorProfileUpsert
) -> InvestorProfileResponse:
    """Save thesis / credentials. Does not change KYC — Stripe does."""
    require_investor(actor)
    if actor.role is Role.ADMIN:
        raise ForbiddenError("Admins do not hold an investor thesis.")

    repo = InvestorProfileRepository(session)
    profile = await repo.get_by_user(actor.id)
    country = payload.country.upper() if payload.country else None
    currency = payload.ticket_currency.upper() if payload.ticket_currency else None
    stages = [s.value for s in payload.thesis_stages]
    geos = [g.upper() for g in payload.thesis_geographies]

    if profile is None:
        profile = await repo.add(
            InvestorProfile(
                user_id=actor.id,
                firm=payload.firm,
                investor_type=payload.investor_type,
                country=country,
                linkedin_url=payload.linkedin_url,
                thesis_sectors=list(payload.thesis_sectors),
                thesis_stages=stages,
                thesis_geographies=geos,
                ticket_min_minor=payload.ticket_min_minor,
                ticket_max_minor=payload.ticket_max_minor,
                ticket_currency=currency,
                risk_notes=payload.risk_notes,
            )
        )
    else:
        profile.firm = payload.firm
        profile.investor_type = payload.investor_type
        profile.country = country
        profile.linkedin_url = payload.linkedin_url
        profile.thesis_sectors = list(payload.thesis_sectors)
        profile.thesis_stages = stages
        profile.thesis_geographies = geos
        profile.ticket_min_minor = payload.ticket_min_minor
        profile.ticket_max_minor = payload.ticket_max_minor
        profile.ticket_currency = currency
        profile.risk_notes = payload.risk_notes
        await session.flush()

    user = await UserRepository(session).get_by_id(actor.id)
    status = user.kyc_status if user is not None else actor.kyc_status
    return _profile_response(profile, status)


async def start_identity_session(
    session: AsyncSession,
    actor: CurrentUser,
    *,
    settings: Settings | None = None,
) -> IdentitySessionResponse:
    """Create a Stripe Identity VerificationSession for the investor."""
    require_investor(actor)
    if actor.role is Role.ADMIN:
        raise ForbiddenError("Admins are not KYC'd as investors.")

    settings = settings or get_settings()
    key = settings.stripe_secret_key
    if key is None or not key.get_secret_value().strip():
        raise ConfigurationError

    users = UserRepository(session)
    user = await users.get_by_id(actor.id)
    if user is None:
        raise NotFoundError
    if user.kyc_status is KycStatus.VERIFIED:
        raise InvalidRequestError(
            "Identity is already verified.",
            {"reason": "already_verified"},
        )

    stripe.api_key = key.get_secret_value()
    return_url = (
        f"{settings.app_link_base_url.rstrip('/')}/investor/verify?identity=done"
    )
    verification = stripe.identity.VerificationSession.create(
        type="document",
        metadata={"user_id": str(user.id)},
        options={"document": {"require_matching_selfie": True}},
        return_url=return_url,
    )
    session_id = str(verification.id)
    url = verification.url
    if not url:
        raise ConfigurationError

    user.stripe_identity_session_id = session_id
    if user.kyc_status is KycStatus.NONE:
        user.kyc_status = KycStatus.PENDING
        await record_action(
            session,
            AuditAction.KYC_STATUS_CHANGED,
            actor_id=None,
            target_type="user",
            target_id=str(user.id),
            details={"from": KycStatus.NONE.value, "to": KycStatus.PENDING.value},
        )
    await session.flush()
    return IdentitySessionResponse(
        url=url, session_id=session_id, kyc_status=user.kyc_status.value
    )


async def apply_identity_webhook_event(
    session: AsyncSession, event_type: str, payload: dict[str, Any]
) -> None:
    """Map Stripe Identity events onto `users.kyc_status`."""
    user_id_raw = (payload.get("metadata") or {}).get("user_id")
    if not user_id_raw:
        logger.warning("identity event missing user_id")
        return
    try:
        user_id = uuid.UUID(str(user_id_raw))
    except ValueError:
        return

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        return

    previous = user.kyc_status
    if event_type == "identity.verification_session.verified":
        user.kyc_status = KycStatus.VERIFIED
    elif event_type in (
        "identity.verification_session.requires_input",
        "identity.verification_session.canceled",
    ):
        user.kyc_status = KycStatus.FAILED
    else:
        return

    session_id = payload.get("id")
    if session_id:
        user.stripe_identity_session_id = str(session_id)
    await session.flush()

    if previous is not user.kyc_status:
        await record_action(
            session,
            AuditAction.KYC_STATUS_CHANGED,
            actor_id=None,
            target_type="user",
            target_id=str(user.id),
            details={
                "from": previous.value,
                "to": user.kyc_status.value,
                "source": "stripe_identity",
                "event": event_type,
            },
        )
        if user.kyc_status is KycStatus.VERIFIED:
            try:
                from app.modules.notifications import service as notifications

                await notifications.notify_kyc_verified(
                    session, user_id=user.id, app_url=get_settings().app_link_base_url
                )
            except Exception:  # noqa: BLE001 — notification must not fail webhook
                logger.exception("kyc verified notification failed")


async def watchlist(session: AsyncSession, actor: CurrentUser) -> WatchlistResponse:
    require_investor(actor)
    require_kyc(actor)
    ids = await WatchlistRepository(session).list_ids(actor.id)
    return WatchlistResponse(startup_ids=ids)


async def toggle_watch(
    session: AsyncSession, actor: CurrentUser, startup_id: uuid.UUID
) -> WatchlistResponse:
    require_investor(actor)
    require_kyc(actor)
    await visible_startup(session, actor, startup_id)
    ids = await WatchlistRepository(session).toggle(actor.id, startup_id)
    return WatchlistResponse(startup_ids=ids)


async def analyst_chat(
    session: AsyncSession,
    actor: CurrentUser,
    startup_id: uuid.UUID,
    message: str,
    history: list[ChatTurn],
    *,
    client: AiClient | None = None,
) -> MentorChatResponse:
    """Investor analyst chat — summary-tier retrieval only (T4.4)."""
    require_investor(actor)
    require_kyc(actor)

    card = await visible_startup(session, actor, startup_id)
    run = await AuditRunRepository(session).get(card.audit_run_id)
    if run is None or run.status is not AuditStatus.SUCCEEDED or not run.report:
        raise InvalidRequestError("No summary available for this startup.")

    # Enforce summary tier in retrieval — never pass the stored full report.
    summary = summary_report(run.report).model_dump(mode="json")
    context = {
        "startup_id": str(card.startup_id),
        "name": card.name,
        "sector": card.sector,
        "stage": card.stage.value if card.stage else None,
        "country": card.country,
        "summary": summary,
    }
    history_block = "\n".join(f"{t.role.value}: {t.content}" for t in history[-10:])
    user_payload = (
        f"SUMMARY_CONTEXT:\n{json.dumps(context, default=str)}\n\n"
        f"PRIOR_TURNS:\n{history_block or '(none)'}\n\n"
        f"INVESTOR_QUESTION:\n{message.strip()}"
    )
    fenced = fence(user_payload, label="investor_analyst_turn")
    ai = client or AiClient(get_settings())
    result = await ai.complete(
        tier=ModelTier.CHAT,
        prompt=ANALYST_SYSTEM_V1,
        schema=MentorReplyOut,
        system=uncached_system(UNTRUSTED_RULE, ANALYST_SYSTEM_V1.text),
        messages=[{"role": "user", "content": fenced.text}],
        user_id=str(actor.id),
    )
    out = result.output
    return MentorChatResponse(
        reply=out.reply,
        citations=[
            MentorCitation(kind=CitationKind(c.kind.value), ref=c.ref)
            for c in out.citations
        ],
    )
