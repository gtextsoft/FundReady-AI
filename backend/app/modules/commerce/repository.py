"""Commerce persistence.

Layer: **repository** (ARCHITECTURE.md section 3) -- queries only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.commerce.models import (
    Purchase,
    PurchaseKind,
    PurchaseStatus,
    StripeWebhookEvent,
)


class PurchaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, purchase: Purchase) -> Purchase:
        self._session.add(purchase)
        await self._session.flush()
        return purchase

    async def get_by_session_id(self, session_id: str) -> Purchase | None:
        result = await self._session.execute(
            select(Purchase).where(Purchase.stripe_checkout_session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def latest_completed_unlock(self, user_id: uuid.UUID) -> Purchase | None:
        result = await self._session.execute(
            select(Purchase)
            .where(
                Purchase.user_id == user_id,
                Purchase.kind == PurchaseKind.UNLOCK,
                Purchase.status == PurchaseStatus.COMPLETED,
            )
            .order_by(Purchase.completed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def mark_completed(
        self,
        purchase: Purchase,
        *,
        payment_intent_id: str | None,
        amount_minor: int,
        currency: str,
    ) -> Purchase:
        purchase.status = PurchaseStatus.COMPLETED
        purchase.stripe_payment_intent_id = payment_intent_id
        purchase.amount_minor = amount_minor
        purchase.currency = currency.upper()
        purchase.completed_at = datetime.now(UTC)
        await self._session.flush()
        return purchase


class StripeWebhookEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, event_id: str) -> StripeWebhookEvent | None:
        return await self._session.get(StripeWebhookEvent, event_id)

    async def record(self, event_id: str, event_type: str) -> StripeWebhookEvent:
        row = StripeWebhookEvent(id=event_id, type=event_type)
        self._session.add(row)
        await self._session.flush()
        return row
