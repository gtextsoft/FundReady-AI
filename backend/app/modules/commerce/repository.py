"""Commerce persistence.

Layer: **repository** (ARCHITECTURE.md section 3) -- queries only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.commerce.models import (
    Product,
    ProductEnrolment,
    ProductKind,
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


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, product: Product) -> Product:
        self._session.add(product)
        await self._session.flush()
        return product

    async def get(self, product_id: uuid.UUID) -> Product | None:
        return await self._session.get(Product, product_id)

    async def get_by_slug(self, slug: str) -> Product | None:
        result = await self._session.execute(
            select(Product).where(Product.slug == slug)
        )
        return result.scalar_one_or_none()

    def _filtered(
        self,
        *,
        region: str | None,
        kind: ProductKind | None,
        active_only: bool,
    ) -> Select[tuple[Product]]:
        stmt = select(Product)
        if active_only:
            stmt = stmt.where(Product.active.is_(True))
        if kind is not None:
            stmt = stmt.where(Product.kind == kind)
        if region is not None:
            code = region.strip().upper()
            stmt = stmt.where(
                or_(
                    Product.regions.contains([code]),
                    Product.regions.contains(["*"]),
                )
            )
        return stmt

    async def list_products(
        self,
        *,
        region: str | None = None,
        kind: ProductKind | None = None,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Product], int]:
        base = self._filtered(region=region, kind=kind, active_only=active_only)
        total = await self._session.scalar(
            select(func.count()).select_from(base.subquery())
        )
        result = await self._session.execute(
            base.order_by(Product.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), int(total or 0)


class ProductEnrolmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, enrolment: ProductEnrolment) -> ProductEnrolment:
        self._session.add(enrolment)
        await self._session.flush()
        return enrolment

    async def get(
        self, user_id: uuid.UUID, product_id: uuid.UUID
    ) -> ProductEnrolment | None:
        result = await self._session.execute(
            select(ProductEnrolment).where(
                ProductEnrolment.user_id == user_id,
                ProductEnrolment.product_id == product_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[ProductEnrolment], int]:
        base = select(ProductEnrolment).where(ProductEnrolment.user_id == user_id)
        total = await self._session.scalar(
            select(func.count()).select_from(base.subquery())
        )
        result = await self._session.execute(
            base.order_by(ProductEnrolment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), int(total or 0)


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
