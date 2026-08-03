"""Investor data access (T4.3).

Layer: **repository** (ARCHITECTURE.md section 3) -- database access only.
Queries in, models/data out. No business rules, no authorization decisions.

**One deliberate exception to that rule.** The discovery query filters on
`investor_visible` in SQL rather than leaving it to the service. Everywhere else
authorization is a service decision (D13) and repositories return unfiltered
rows -- but visibility here is not a check about *the caller*, it is part of
what the collection *is*: "startups that opted in to being discovered". A row
that has not opted in is not a row this query is about.

The practical reason is the one that matters. Discovery is a list endpoint over
other people's confidential businesses, and a filter applied after the fact is
one forgotten call away from publishing every founder on the platform. In SQL it
cannot be forgotten: there is no unfiltered variant of this query to reach for
by mistake.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditRun
from app.modules.audit.runs import AuditStatus
from app.modules.intake.models import StartupProfile
from app.modules.investor.schemas import DiscoveryFilters

__all__ = ["DiscoveryRepository"]


class DiscoveryRepository:
    """Startups that have opted in to being discovered."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _visible(self) -> Select[tuple[StartupProfile, AuditRun]]:
        """Opted-in profiles joined to their most recent succeeded audit.

        The join is **inner**, so a profile that opted in but has no succeeded
        audit does not appear. There would be nothing to show but a name, and a
        card with no verdict invites an investor to go and ask the founder
        directly -- the one thing the brokerage exists to prevent.

        `DISTINCT ON` picks the newest run per startup in a single pass. The
        alternative reads every audit of every visible startup to render one
        row each.
        """
        latest = (
            select(AuditRun)
            .where(AuditRun.status == AuditStatus.SUCCEEDED)
            .where(AuditRun.report.isnot(None))
            .distinct(AuditRun.startup_id)
            .order_by(AuditRun.startup_id, AuditRun.created_at.desc())
            .subquery()
        )
        return (
            select(StartupProfile, AuditRun)
            .join(latest, latest.c.startup_id == StartupProfile.id)
            .join(AuditRun, AuditRun.id == latest.c.id)
            .where(StartupProfile.investor_visible.is_(True))
        )

    def _apply(
        self,
        statement: Select[tuple[StartupProfile, AuditRun]],
        filters: DiscoveryFilters,
    ) -> Select[tuple[StartupProfile, AuditRun]]:
        if filters.sector:
            # Case-insensitive because sector is free text (D11). A founder who
            # typed "Fintech" and an investor who filtered "fintech" mean the
            # same thing; an exact match would silently return nothing.
            statement = statement.where(
                func.lower(StartupProfile.sector) == filters.sector.strip().lower()
            )
        if filters.stage is not None:
            statement = statement.where(StartupProfile.stage == filters.stage)
        if filters.country:
            statement = statement.where(
                func.upper(StartupProfile.country) == filters.country.strip().upper()
            )
        return statement

    async def search(
        self, filters: DiscoveryFilters, *, limit: int, offset: int
    ) -> Sequence[tuple[StartupProfile, AuditRun]]:
        statement = (
            self._apply(self._visible(), filters)
            .order_by(StartupProfile.published_at.desc().nullslast(), StartupProfile.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.tuples())

    async def count(self, filters: DiscoveryFilters) -> int:
        """Total matching rows, so a client can render "page N of M"."""
        inner = self._apply(self._visible(), filters).subquery()
        total = await self._session.scalar(select(func.count()).select_from(inner))
        return int(total or 0)

    async def visible_run(
        self, startup_id: uuid.UUID
    ) -> tuple[StartupProfile, AuditRun] | None:
        """One discoverable startup and the audit its card was built from.

        Reusing `_visible()` is the point: an investor cannot act on a startup
        that is not discoverable by pasting its id, because the same filter
        guards the read and every write that follows from it.
        """
        result = await self._session.execute(
            self._visible().where(StartupProfile.id == startup_id)
        )
        return result.tuples().first()
