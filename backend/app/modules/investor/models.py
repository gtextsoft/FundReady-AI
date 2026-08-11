"""Investor ORM tables (T4.1).

Layer: **models** — SQLAlchemy table definitions only.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

__all__ = ["InvestorProfile", "WatchlistEntry"]


class InvestorProfile(Base):
    """Thesis and firm details for one investor account.

    KYC status lives on `users.kyc_status` (trusted from Stripe). This row is
    the investor's self-declared thesis used for discovery ranking (T4.3).
    """

    __tablename__ = "investor_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    firm: Mapped[str | None] = mapped_column(String(200))
    investor_type: Mapped[str | None] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(2))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))

    thesis_sectors: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    thesis_stages: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    thesis_geographies: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )

    ticket_min_minor: Mapped[int | None] = mapped_column(BigInteger)
    ticket_max_minor: Mapped[int | None] = mapped_column(BigInteger)
    ticket_currency: Mapped[str | None] = mapped_column(String(3))
    risk_notes: Mapped[str | None] = mapped_column(String(2000))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WatchlistEntry(Base):
    """Synced watchlist for one investor (replaces device-local SecureStore)."""

    __tablename__ = "watchlist_entries"
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
