"""Investor data access (T4.1, T4.3).

Layer: **repository** (ARCHITECTURE.md section 3) -- database access only.
Queries in, models/data out. No business rules, no authorization decisions.

**One deliberate exception to that rule.** The discovery query filters on
`investor_visible` in SQL rather than leaving it to the service. Everywhere else
authorization is a service decision (D13) and repositories return unfiltered
rows -- but visibility here is not a check about *the caller*, it is part of
what the collection *is*: "startups that opted in to being discovered". A row
that has not opted in is not a row this query is about.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditRun
from app.modules.audit.runs import AuditStatus
from app.modules.intake.models import StartupProfile
from app.modules.investor.models import InvestorProfile, WatchlistEntry
from app.modules.investor.schemas import DiscoveryFilters
from app.modules.readiness.generation import Requirement, TaskStatus
from app.modules.readiness.models import ReadinessTask

__all__ = ["DiscoveryRepository", "InvestorProfileRepository", "WatchlistRepository"]


class InvestorProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user(self, user_id: uuid.UUID) -> InvestorProfile | None:
        result = await self._session.execute(
            select(InvestorProfile).where(InvestorProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def add(self, profile: InvestorProfile) -> InvestorProfile:
        self._session.add(profile)
        await self._session.flush()
        return profile


class WatchlistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_ids(self, investor_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self._session.execute(
            select(WatchlistEntry.startup_id)
            .where(WatchlistEntry.investor_id == investor_id)
            .order_by(WatchlistEntry.created_at.desc())
        )
        return list(result.scalars().all())

    async def toggle(
        self, investor_id: uuid.UUID, startup_id: uuid.UUID
    ) -> list[uuid.UUID]:
        existing = await self._session.execute(
            select(WatchlistEntry).where(
                WatchlistEntry.investor_id == investor_id,
                WatchlistEntry.startup_id == startup_id,
            )
        )
        row = existing.scalar_one_or_none()
        if row is None:
            self._session.add(
                WatchlistEntry(investor_id=investor_id, startup_id=startup_id)
            )
        else:
            await self._session.execute(
                delete(WatchlistEntry).where(WatchlistEntry.id == row.id)
            )
        await self._session.flush()
        return await self.list_ids(investor_id)


class DiscoveryRepository:
    """Startups that have opted in to being discovered."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _visible(self) -> Select[tuple[StartupProfile, AuditRun]]:
        """Opted-in profiles that have cleared the readiness gate (T3.6)."""
        latest = (
            select(AuditRun)
            .where(AuditRun.status == AuditStatus.SUCCEEDED)
            .where(AuditRun.report.isnot(None))
            .distinct(AuditRun.startup_id)
            .order_by(
                AuditRun.startup_id, AuditRun.created_at.desc(), AuditRun.id.desc()
            )
            .subquery()
        )
        outstanding = (
            select(ReadinessTask.id)
            .where(
                ReadinessTask.startup_id == StartupProfile.id,
                ReadinessTask.audit_run_id == latest.c.id,
                ReadinessTask.requirement == Requirement.REQUIRED,
                ReadinessTask.status.not_in((TaskStatus.PASSED, TaskStatus.OBSOLETE)),
            )
            .exists()
        )
        return (
            select(StartupProfile, AuditRun)
            .join(latest, latest.c.startup_id == StartupProfile.id)
            .join(AuditRun, AuditRun.id == latest.c.id)
            .where(StartupProfile.investor_visible.is_(True))
            .where(~outstanding)
        )

    def _apply(
        self,
        statement: Select[tuple[StartupProfile, AuditRun]],
        filters: DiscoveryFilters,
    ) -> Select[tuple[StartupProfile, AuditRun]]:
        if filters.sector:
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
        result = await self._session.execute(
            self._visible().where(StartupProfile.id == startup_id)
        )
        return result.tuples().first()
