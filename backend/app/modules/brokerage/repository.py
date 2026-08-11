"""Brokerage data access (T4.5, T4.6).

Layer: **repository** (ARCHITECTURE.md section 3) -- database access only.
Queries in, models/data out. No business rules, no authorization decisions.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.brokerage.models import (
    CallRequest,
    Interest,
    InterestStatus,
    Meeting,
    ReportReveal,
)

__all__ = [
    "CallRequestRepository",
    "InterestRepository",
    "MeetingRepository",
    "RevealRepository",
]


class InterestRepository:
    """Expressions of interest, and the decisions taken on them."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, interest_id: uuid.UUID) -> Interest | None:
        return await self._session.get(Interest, interest_id)

    async def for_pair(
        self, investor_id: uuid.UUID, startup_id: uuid.UUID
    ) -> Interest | None:
        """The existing interest for this pair, if any.

        Checked before insert so a repeat expression returns the original row
        rather than tripping `uq_interest_pair` -- the constraint is the
        guarantee, this is the courtesy.
        """
        found: Interest | None = await self._session.scalar(
            select(Interest).where(
                Interest.investor_id == investor_id,
                Interest.startup_id == startup_id,
            )
        )
        return found

    async def list_for_investor(
        self, investor_id: uuid.UUID, *, limit: int = 100
    ) -> Sequence[Interest]:
        result = await self._session.scalars(
            select(Interest)
            .where(Interest.investor_id == investor_id)
            .order_by(Interest.created_at.desc())
            .limit(limit)
        )
        return list(result)

    async def list_all(
        self, *, status: InterestStatus | None = None, limit: int = 100
    ) -> Sequence[Interest]:
        """Every interest, for the SACI queue. Oldest first.

        Ascending, unlike the investor's own list: this is a work queue and the
        one waiting longest is the one to deal with next.
        """
        statement = select(Interest).order_by(Interest.created_at).limit(limit)
        if status is not None:
            statement = statement.where(Interest.status == status)
        return list(await self._session.scalars(statement))

    async def create(
        self, *, investor_id: uuid.UUID, startup_id: uuid.UUID, note: str | None
    ) -> Interest:
        interest = Interest(investor_id=investor_id, startup_id=startup_id, note=note)
        self._session.add(interest)
        await self._session.flush()
        return interest


class RevealRepository:
    """Full-report disclosures. Append-only in practice -- nothing deletes one."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for(
        self, interest_id: uuid.UUID, audit_run_id: uuid.UUID
    ) -> ReportReveal | None:
        found: ReportReveal | None = await self._session.scalar(
            select(ReportReveal).where(
                ReportReveal.interest_id == interest_id,
                ReportReveal.audit_run_id == audit_run_id,
            )
        )
        return found

    async def list_for_interest(self, interest_id: uuid.UUID) -> Sequence[ReportReveal]:
        """Every run revealed under this interest, newest first.

        Plural because a founder who re-audits produces a new report, and SACI
        may reveal that one too. Each disclosure is its own row naming its own
        run -- an investor's access is to the runs actually shown to them, not
        to "this startup's reports" in general.
        """
        return list(
            await self._session.scalars(
                select(ReportReveal)
                .where(ReportReveal.interest_id == interest_id)
                .order_by(ReportReveal.revealed_at.desc())
            )
        )

    async def create(
        self,
        *,
        interest_id: uuid.UUID,
        audit_run_id: uuid.UUID,
        revealed_by_id: uuid.UUID,
    ) -> ReportReveal:
        reveal = ReportReveal(
            interest_id=interest_id,
            audit_run_id=audit_run_id,
            revealed_by_id=revealed_by_id,
        )
        self._session.add(reveal)
        await self._session.flush()
        return reveal


class MeetingRepository:
    """SACI-scheduled introduction meetings. One per interest at most."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, meeting_id: uuid.UUID) -> Meeting | None:
        return await self._session.get(Meeting, meeting_id)

    async def for_interest(self, interest_id: uuid.UUID) -> Meeting | None:
        found: Meeting | None = await self._session.scalar(
            select(Meeting).where(Meeting.interest_id == interest_id)
        )
        return found

    async def list_for_interest(self, interest_id: uuid.UUID) -> Sequence[Meeting]:
        return list(
            await self._session.scalars(
                select(Meeting)
                .where(Meeting.interest_id == interest_id)
                .order_by(Meeting.scheduled_at.desc())
            )
        )

    async def create(
        self,
        *,
        interest_id: uuid.UUID,
        scheduled_at: datetime,
        duration_minutes: int,
        location: str | None,
        notes: str | None,
        created_by_id: uuid.UUID,
    ) -> Meeting:
        meeting = Meeting(
            interest_id=interest_id,
            scheduled_at=scheduled_at,
            duration_minutes=duration_minutes,
            location=location,
            notes=notes,
            created_by_id=created_by_id,
        )
        self._session.add(meeting)
        await self._session.flush()
        return meeting


class CallRequestRepository:
    """Investor-proposed virtual calls the founder answers."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, call_id: uuid.UUID) -> CallRequest | None:
        return await self._session.get(CallRequest, call_id)

    async def list_all(self, *, limit: int = 100) -> Sequence[CallRequest]:
        return list(
            await self._session.scalars(
                select(CallRequest).order_by(CallRequest.created_at.desc()).limit(limit)
            )
        )

    async def list_for_investor(
        self, investor_id: uuid.UUID, *, limit: int = 100
    ) -> Sequence[CallRequest]:
        """Calls on interests this investor owns, newest first."""
        return list(
            await self._session.scalars(
                select(CallRequest)
                .join(Interest, Interest.id == CallRequest.interest_id)
                .where(Interest.investor_id == investor_id)
                .order_by(CallRequest.created_at.desc())
                .limit(limit)
            )
        )

    async def list_for_startup(
        self, startup_id: uuid.UUID, *, limit: int = 100
    ) -> Sequence[CallRequest]:
        """Calls against interests on this startup, newest first."""
        return list(
            await self._session.scalars(
                select(CallRequest)
                .join(Interest, Interest.id == CallRequest.interest_id)
                .where(Interest.startup_id == startup_id)
                .order_by(CallRequest.created_at.desc())
                .limit(limit)
            )
        )

    async def create(
        self,
        *,
        interest_id: uuid.UUID,
        requested_by_id: uuid.UUID,
        proposed_at: datetime,
        message: str | None,
    ) -> CallRequest:
        call = CallRequest(
            interest_id=interest_id,
            requested_by_id=requested_by_id,
            proposed_at=proposed_at,
            message=message,
        )
        self._session.add(call)
        await self._session.flush()
        return call
