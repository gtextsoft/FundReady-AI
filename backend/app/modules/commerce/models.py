"""Commerce ORM tables.

Layer: **models** (ARCHITECTURE.md section 3) -- SQLAlchemy table definitions
only. Every schema change also requires an Alembic migration under
`migrations/`; the database is never hand-edited.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _by_value(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class ProductKind(StrEnum):
    """Catalogue discriminator (DECISIONS.md D18). Events carry date/location."""

    PROGRAM = "program"
    MENTORSHIP = "mentorship"
    EVENT = "event"


class PurchaseKind(StrEnum):
    """What was bought. Unlock is D24; catalogue is T3.2 / D18."""

    UNLOCK = "unlock"
    CATALOGUE = "catalogue"


class PurchaseStatus(StrEnum):
    """Lifecycle of one Checkout payment."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class Product(Base):
    """One catalogue item SACI lists and optionally sells (T3.2, D18).

    Programs, mentorship, and events share tags, region relevance, pricing,
    and the path from a readiness gap to a purchase. Events add a start time
    and a location; everything else is the same row.
    """

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[ProductKind] = mapped_column(
        SAEnum(
            ProductKind,
            native_enum=False,
            length=32,
            name="product_kind",
            values_callable=_by_value,
        ),
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    regions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    gap_tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    amount_minor: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))
    stripe_price_id: Mapped[str | None] = mapped_column(String(255))
    event_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_location: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Product {self.slug} {self.kind} active={self.active}>"


class Enrolment(Base):
    """A founder taking a catalogue item (free immediately, paid after webhook)."""

    __tablename__ = "enrolments"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_enrolments_user_product"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Purchase(Base):
    """One founder Checkout purchase, keyed to Stripe's session and payment intent.

    Entitlement (`users.subscription_status`) is derived from completed unlock
    rows via the webhook handler — this table is the ledger, not a client-facing
    source of truth the app invents. Catalogue rows grant an `Enrolment`
    instead of platform unlock.
    """

    __tablename__ = "purchases"
    __table_args__ = (
        UniqueConstraint("stripe_checkout_session_id", name="uq_purchases_session"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), index=True
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
    entitlement (CLAUDE.md section 4, DECISIONS.md D24).
    """

    __tablename__ = "stripe_webhook_events"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    type: Mapped[str] = mapped_column(String(128), index=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


__all__ = [
    "Enrolment",
    "Product",
    "ProductKind",
    "Purchase",
    "PurchaseKind",
    "PurchaseStatus",
    "StripeWebhookEvent",
]
