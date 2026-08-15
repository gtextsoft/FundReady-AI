"""Brokerage ORM tables (T4.5, T4.6).

Layer: **models** (ARCHITECTURE.md section 3) -- SQLAlchemy table definitions
only. Every schema change also requires an Alembic migration under
`migrations/`; the database is never hand-edited.

**SACI is the broker, and these two tables are what that means in code.** An
investor never reaches a founder's full report by their own entitlement. They
express interest; a SACI admin decides; and only a deliberate reveal opens one
full report to one investor. Every step is a row here, which is what makes the
brokerage auditable after the fact rather than a policy nobody can check.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

__all__ = [
    "Interest",
    "InterestStatus",
    "Meeting",
    "MeetingStatus",
    "ReportReveal",
]


class InterestStatus(StrEnum):
    """Where one expression of interest has got to.

    Clients branch on these, so they are stable strings.
    """

    PENDING = "pending"
    """Waiting on SACI. The investor can see nothing new yet."""

    APPROVED = "approved"
    """SACI agreed to broker this. **Approval is not a reveal** -- it means a
    conversation may proceed; the full report is a separate, later action."""

    DECLINED = "declined"
    """SACI will not broker this one. Terminal."""

    WITHDRAWN = "withdrawn"
    """The investor changed their mind. Terminal, and set by the investor."""


class Interest(Base):
    """One investor asking SACI to introduce them to one startup.

    **Not a message to the founder.** The founder is not notified and cannot
    read this row: SACI brokers, and an investor who could contact founders
    directly would be routing around the entire product.
    """

    __tablename__ = "interests"
    __table_args__ = (
        # One interest per investor per startup. Without it, "express interest"
        # is a button an investor can hold down, and every row is something a
        # human at SACI has to triage.
        UniqueConstraint("investor_id", "startup_id", name="uq_interest_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    investor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    startup_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("startup_profiles.id", ondelete="CASCADE"), index=True
    )

    status: Mapped[InterestStatus] = mapped_column(
        SAEnum(
            InterestStatus,
            native_enum=False,
            length=16,
            name="interest_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=InterestStatus.PENDING,
        server_default=InterestStatus.PENDING.value,
        index=True,
    )

    note: Mapped[str | None] = mapped_column(String(1000))
    """What the investor told SACI. **Seen by SACI only, never the founder** --
    an investor writes differently knowing the subject is not reading."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        # `SET NULL`, not `CASCADE`: an admin leaving must not delete the record
        # that a decision was made. The immutable audit log holds who; this
        # column is a convenience for the admin console.
        ForeignKey("users.id", ondelete="SET NULL")
    )

    def __repr__(self) -> str:
        return f"<Interest {self.id} status={self.status.value}>"


class ReportReveal(Base):
    """One SACI admin opening one full report to one investor.

    **The single most consequential write in the platform.** Everything else
    about report tiers is a serializer refusing to emit a field; this is the
    deliberate exception `CLAUDE.md` section 4 permits, and only as an explicit
    admin action. So it is a row rather than a flag: who revealed what, to whom,
    and when -- kept even if the interest is later withdrawn.

    **Scoped to an audit run, not to a startup.** A founder who re-audits after
    fixing their figures has produced a new report, and an investor shown the
    old one has no claim on the new one. The reveal names the exact run whose
    contents were disclosed.
    """

    __tablename__ = "report_reveals"
    __table_args__ = (
        # Revealing twice is a no-op, not a second disclosure -- enforced here
        # rather than only in the service.
        UniqueConstraint("interest_id", "audit_run_id", name="uq_reveal_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    interest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interests.id", ondelete="CASCADE"), index=True
    )
    audit_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="CASCADE"), index=True
    )

    revealed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    revealed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        return f"<ReportReveal {self.id} run={self.audit_run_id}>"


class MeetingStatus(StrEnum):
    PROPOSED = "proposed"
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"


class Meeting(Base):
    """A SACI-brokered meeting. SACI is a required participant."""

    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    interest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interests.id", ondelete="CASCADE"), index=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int]
    location: Mapped[str | None] = mapped_column(String(400))
    notes: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[MeetingStatus] = mapped_column(
        SAEnum(
            MeetingStatus,
            native_enum=False,
            length=16,
            name="meeting_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=MeetingStatus.SCHEDULED,
        server_default=MeetingStatus.SCHEDULED.value,
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
