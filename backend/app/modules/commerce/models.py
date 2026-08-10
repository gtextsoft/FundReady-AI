"""Commerce ORM tables.

Layer: **models** (ARCHITECTURE.md section 3) -- SQLAlchemy table definitions
only. Every schema change also requires an Alembic migration under
`migrations/`; the database is never hand-edited.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _by_value(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class PurchaseKind(StrEnum):
    """What was bought. Unlock is v1 (DECISIONS.md D21); catalogue kinds follow."""

    UNLOCK = "unlock"


class PurchaseStatus(StrEnum):
    """Lifecycle of one Checkout payment."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class Purchase(Base):
    """One founder Checkout purchase, keyed to Stripe's session and payment intent.

    Entitlement (`users.subscription_status`) is derived from completed unlock
    rows via the webhook handler — this table is the ledger, not a client-facing
    source of truth the app invents.
    """

    __tablename__ = "purchases"
    __table_args__ = (
        UniqueConstraint("stripe_checkout_session_id", name="uq_purchases_session"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[PurchaseKind] = mapped_column(
        SAEnum(
            PurchaseKind,
            native_enum=False,
            length=32,
            name="purchase_kind",
            values_callable=_by_value,
        ),
        default=PurchaseKind.UNLOCK,
    )
    status: Mapped[PurchaseStatus] = mapped_column(
        SAEnum(
            PurchaseStatus,
            native_enum=False,
            length=16,
            name="purchase_status",
            values_callable=_by_value,
        ),
        default=PurchaseStatus.PENDING,
        index=True,
    )
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    stripe_checkout_session_id: Mapped[str] = mapped_column(String(255))
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StripeWebhookEvent(Base):
    """Idempotency store for Stripe webhook deliveries.

    Stripe retries; processing the same `event.id` twice must not double-grant
    entitlement (CLAUDE.md section 4, DECISIONS.md D21).
    """

    __tablename__ = "stripe_webhook_events"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    type: Mapped[str] = mapped_column(String(128), index=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


__all__ = [
    "Purchase",
    "PurchaseKind",
    "PurchaseStatus",
    "StripeWebhookEvent",
]
