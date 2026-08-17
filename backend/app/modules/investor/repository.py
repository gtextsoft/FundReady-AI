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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditRun
from app.modules.audit.runs import AuditStatus
from app.modules.intake.models import StartupProfile
from app.modules.investor.models import (
    InvestorProfile,
    ThesisReviewStatus,
    WatchlistItem,
)
from app.modules.investor.schemas import DiscoveryFilters
from app.modules.readiness.generation import Requirement, TaskStatus
from app.modules.readiness.models import ReadinessTask

__all__ = ["DiscoveryRepository", "InvestorProfileRepository", "WatchlistRepository"]


class DiscoveryRepository:
    """Startups that have opted in to being discovered."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _visible(self) -> Select[tuple[StartupProfile, AuditRun]]:
        """Opted-in profiles that have cleared the readiness gate (T3.6).

        Three conditions, and all three are in SQL for the reason the module
        docstring gives: there is no unfiltered variant of this query to reach
        for by mistake.

        * **Opted in.** `investor_visible` is the founder's consent.
        * **Audited.** The join is **inner**, so a profile that opted in but has
          no succeeded audit does not appear. There would be nothing to show but
          a name, and a card with no verdict invites an investor to go and ask
          the founder directly -- the one thing the brokerage exists to prevent.
        * **No required task outstanding.** PRD section 4.2: a startup becomes
          investor-visible when the audit clears **and** all required tasks
          pass.

        **The gate is enforced at the read, not at `publish`.** Consent and
        eligibility are different questions and go stale on different schedules:
        a founder who was eligible when they published is not eligible after a
        re-audit raises a new required gap, and a check written at publish time
        would keep them discoverable anyway. Deciding it here means the answer
        cannot be out of date, and `intake.set_discoverability` stays what it
        already documents itself to be -- consent, unconditional to give and to
        withdraw.

        **Outstanding is scoped to the tasks the *latest* run raised**, which is
        what `audit_run_id` is maintained for: `readiness` refreshes it to the
        newest run on every regeneration, so matching `latest.c.id` means
        "outstanding according to the report an investor would actually be
        shown". Counting every task ever raised instead would strand founders
        permanently -- a task that was graded `failed` keeps that status even
        after a later audit stops raising the gap (`UNTOUCHED_STATUSES` retires
        only untouched rows, deliberately, so evidence is never erased), and a
        gap absent from the current report is one no new evidence can address.
        That founder would have no self-service path back to visibility.

        `obsolete` is excluded as well as `passed`, which is belt-and-braces: a
        task the latest run raised is reopened out of `obsolete` by `_refresh`,
        so the two cannot co-occur today. If that invariant ever breaks, the
        safe direction is not blocking a founder over a retired task.

        `DISTINCT ON` picks the newest run per startup in a single pass. The
        alternative reads every audit of every visible startup to render one
        row each.
        """
        latest = (
            select(AuditRun)
            .where(AuditRun.status == AuditStatus.SUCCEEDED)
            .where(AuditRun.report.isnot(None))
            .distinct(AuditRun.startup_id)
            # `id` breaks the tie, and it is not decoration. Postgres `now()`
            # is the **transaction** timestamp, so two runs written in one
            # transaction share `created_at` to the microsecond -- and with no
            # tiebreaker `DISTINCT ON` then picks between them arbitrarily and
            # not necessarily the same way twice. The gate here and
            # `AuditRunRepository.latest_succeeded` must resolve to the *same*
            # run or a founder is told they have cleared while discovery says
            # otherwise, so both order identically.
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


class InvestorProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID) -> InvestorProfile | None:
        return await self._session.get(InvestorProfile, user_id)

    async def get_or_create(self, user_id: uuid.UUID) -> InvestorProfile:
        row = await self.get(user_id)
        if row is not None:
            return row
        try:
            async with self._session.begin_nested():
                created = InvestorProfile(user_id=user_id)
                self._session.add(created)
                await self._session.flush()
                return created
        except IntegrityError:
            existing = await self.get(user_id)
            if existing is None:
                raise
            return existing

    async def list_for_review(
        self,
        *,
        status: ThesisReviewStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[InvestorProfile], int]:
        statement = select(InvestorProfile)
        if status is not None:
            statement = statement.where(InvestorProfile.review_status == status)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(statement.subquery())
            )
            or 0
        )
        rows = list(
            await self._session.scalars(
                statement.order_by(InvestorProfile.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return rows, total


class WatchlistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_ids(self, investor_id: uuid.UUID) -> list[uuid.UUID]:
        rows = await self._session.scalars(
            select(WatchlistItem.startup_id)
            .where(WatchlistItem.investor_id == investor_id)
            .order_by(WatchlistItem.created_at.desc())
        )
        return list(rows)

    async def get_pair(
        self, investor_id: uuid.UUID, startup_id: uuid.UUID
    ) -> WatchlistItem | None:
        return await self._session.scalar(
            select(WatchlistItem).where(
                WatchlistItem.investor_id == investor_id,
                WatchlistItem.startup_id == startup_id,
            )
        )

    async def add(self, investor_id: uuid.UUID, startup_id: uuid.UUID) -> None:
        self._session.add(
            WatchlistItem(investor_id=investor_id, startup_id=startup_id)
        )
        await self._session.flush()

    async def remove(self, row: WatchlistItem) -> None:
        await self._session.delete(row)
        await self._session.flush()
