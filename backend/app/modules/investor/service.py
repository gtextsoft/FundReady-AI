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

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError
from app.core.security import CurrentUser, Role
from app.modules.investor.repository import DiscoveryRepository
from app.modules.investor.schemas import DiscoveryFilters, DiscoveryPage, StartupCard

__all__ = ["discover", "require_investor", "visible_startup"]

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


async def discover(
    session: AsyncSession,
    actor: CurrentUser,
    filters: DiscoveryFilters,
    *,
    limit: int,
    offset: int,
) -> DiscoveryPage:
    """One page of discoverable startups, at summary tier."""
    require_investor(actor)

    repository = DiscoveryRepository(session)
    rows = await repository.search(filters, limit=limit, offset=offset)
    total = await repository.count(filters)

    return DiscoveryPage(
        items=[StartupCard.of(profile, run) for profile, run in rows],
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
    require_investor(actor)

    row = await DiscoveryRepository(session).visible_run(startup_id)
    if row is None:
        raise NotFoundError(_NOT_DISCOVERABLE)

    profile, run = row
    return StartupCard.of(profile, run)
