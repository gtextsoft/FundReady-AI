"""Investor ORM tables (T4.1)."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _by_value(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class ThesisReviewStatus(StrEnum):
    """Admin review of an investor thesis. Discovery requires `accepted`."""

    NONE = "none"
    IN_REVIEW = "in_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class InvestorProfile(Base):
    """One thesis per investor account."""

    __tablename__ = "investor_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    firm: Mapped[str | None] = mapped_column(String(200))
    investor_type: Mapped[str | None] = mapped_column(String(80))
    country: Mapped[str | None] = mapped_column(String(2))
    linkedin_url: Mapped[str | None] = mapped_column(String(400))
    thesis_sectors: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    thesis_stages: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    thesis_geographies: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    ticket_min_minor: Mapped[int | None] = mapped_column(Integer)
    ticket_max_minor: Mapped[int | None] = mapped_column(Integer)
    ticket_currency: Mapped[str | None] = mapped_column(String(3))
    risk_notes: Mapped[str | None] = mapped_column(String(2000))
    review_status: Mapped[ThesisReviewStatus] = mapped_column(
        SAEnum(
            ThesisReviewStatus,
            native_enum=False,
            length=16,
            name="thesis_review_status",
            values_callable=_by_value,
        ),
        default=ThesisReviewStatus.NONE,
        server_default=ThesisReviewStatus.NONE.value,
        index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )


class WatchlistItem(Base):
    """One investor starring one discoverable startup."""

    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("investor_id", "startup_id", name="uq_watchlist_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    investor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    startup_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("startup_profiles.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
