"""Commerce persistence.

Layer: **repository** (ARCHITECTURE.md section 3) -- queries only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.commerce.matching import GLOBAL_REGION, normalise_region
from app.modules.commerce.models import (
    Enrolment,
    Product,
    ProductKind,
    Purchase,
    PurchaseKind,
    PurchaseStatus,
    StripeWebhookEvent,
)


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

    async def list_page(
        self,
        *,
        region: str | None,
        kind: ProductKind | None,
        include_inactive: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Product], int]:
        query: Select[tuple[Product]] = select(Product)
        if not include_inactive:
            query = query.where(Product.active.is_(True))
        if kind is not None:
            query = query.where(Product.kind == kind)
        if region is not None:
            code = normalise_region(region)
            query = query.where(
                or_(
                    Product.regions.contains([GLOBAL_REGION]),
                    Product.regions.contains([code]),
                )
            )
        total = await self._session.scalar(
            select(func.count()).select_from(query.subquery())
        )
        rows = await self._session.scalars(
            query.order_by(Product.title.asc(), Product.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    async def list_active(self) -> list[Product]:
        rows = await self._session.scalars(
            select(Product)
            .where(Product.active.is_(True))
            .order_by(Product.title.asc(), Product.id.asc())
        )
        return list(rows)


class EnrolmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, enrolment: Enrolment) -> Enrolment:
        self._session.add(enrolment)
        await self._session.flush()
        return enrolment

    async def get_for_user_product(
        self, user_id: uuid.UUID, product_id: uuid.UUID
    ) -> Enrolment | None:
        result = await self._session.execute(
            select(Enrolment).where(
                Enrolment.user_id == user_id,
                Enrolment.product_id == product_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[tuple[Enrolment, Product | None]], int]:
        total = await self._session.scalar(
            select(func.count())
            .select_from(Enrolment)
            .where(Enrolment.user_id == user_id)
        )
        rows = await self._session.execute(
            select(Enrolment, Product)
            .outerjoin(Product, Product.id == Enrolment.product_id)
            .where(Enrolment.user_id == user_id)
            .order_by(Enrolment.created_at.desc(), Enrolment.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [(enrolment, product) for enrolment, product in rows.all()], int(
            total or 0
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
