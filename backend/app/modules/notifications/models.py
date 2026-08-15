"""In-app notification rows (T5.3)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class NotificationKind(StrEnum):
    AUDIT_READY = "audit_ready"
    TASK_ASSIGNED = "task_assigned"
    EVIDENCE_RESULT = "evidence_result"
    MEETING_BOOKED = "meeting_booked"
    INTEREST_DECIDED = "interest_decided"
    COMPANY_VERIFICATION = "company_verification"
    THESIS_REVIEW = "thesis_review"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[NotificationKind] = mapped_column(
        SAEnum(
            NotificationKind,
            native_enum=False,
            length=40,
            name="notification_kind",
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(2000))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
