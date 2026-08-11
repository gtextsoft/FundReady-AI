"""Notifications ORM tables (T5.3).

Layer: **models** (ARCHITECTURE.md section 3) -- SQLAlchemy table definitions
only. Every schema change also requires an Alembic migration under
`migrations/`; the database is never hand-edited.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

__all__ = ["Notification"]


class Notification(Base):
    """One in-app alert for one user.

    Product events (task assigned, evidence result, meeting booked, …) write a
    row here and often also send a transactional email. The inbox is the
    durable record; email is a delivery channel that must not be the only
    place the event exists.
    """

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    kind: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(2000))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
