"""Gap → program matching without an embedding provider (T5.1 / T5.2).

Uses product `gap_tags` and region lists. Choosing Voyage/OpenAI embeddings
remains an open product decision; keyword tags unblock recommendations today
without a new paid dependency (CLAUDE.md §2.5).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError
from app.core.security import CurrentUser, Role
from app.modules.commerce.models import Product
from app.modules.commerce.repository import ProductRepository
from app.modules.intake import service as intake
from app.modules.readiness import service as readiness
from app.modules.recommendation.schemas import RecommendationPage, RecommendedProduct


def _kind_value(product: Product) -> str:
    kind = product.kind
    return kind.value if hasattr(kind, "value") else str(kind)


def _score_product(
    product: Product, tags: set[str], country: str | None
) -> tuple[int, list[str]]:
    product_tags = {str(t).lower() for t in (product.gap_tags or [])}
    matched = sorted(tags & product_tags)
    score = len(matched) * 2
    regions = {str(r).upper() for r in (product.regions or [])}
    if country and ("*" in regions or country.upper() in regions):
        score += 1
    elif country and regions and country.upper() not in regions and "*" not in regions:
        return 0, []
    return score, matched


async def recommend_for_startup(
    session: AsyncSession,
    actor: CurrentUser,
    startup_id: uuid.UUID,
    *,
    limit: int = 20,
) -> RecommendationPage:
    """Recommend catalogue products for a founder's open readiness gaps."""
    if actor.role not in (Role.FOUNDER, Role.ADMIN):
        raise ForbiddenError

    profile = await intake.get_profile(session, actor, startup_id)
    tasks_page = await readiness.list_tasks(
        session, actor, profile.id, limit=100, offset=0
    )
    task_rows, _ = tasks_page
    tags: set[str] = set()
    for task in task_rows:
        if task.status.value in ("passed", "obsolete"):
            continue
        tags.add(task.dimension.value.lower())
        for word in task.action.lower().split():
            if len(word) >= 5:
                tags.add(word)

    products, _ = await ProductRepository(session).list_products(
        region=profile.country, kind=None, limit=100, offset=0
    )
    scored: list[RecommendedProduct] = []
    for product in products:
        score, matched = _score_product(product, tags, profile.country)
        if score <= 0:
            continue
        scored.append(
            RecommendedProduct(
                product_id=product.id,
                slug=product.slug,
                title=product.title,
                kind=_kind_value(product),
                score=score,
                matched_tags=matched,
            )
        )
    scored.sort(key=lambda r: (-r.score, r.title))
    return RecommendationPage(
        items=scored[:limit], country=profile.country
    )


async def recommend_for_country(
    session: AsyncSession,
    actor: CurrentUser,
    *,
    country: str,
    limit: int = 50,
) -> RecommendationPage:
    """Browsable catalogue filtered by country (T5.2)."""
    if actor.role not in (Role.FOUNDER, Role.INVESTOR, Role.ADMIN):
        raise ForbiddenError
    code = country.strip().upper()
    if len(code) != 2:
        raise NotFoundError
    products, _ = await ProductRepository(session).list_products(
        region=code, kind=None, limit=limit, offset=0
    )
    return RecommendationPage(
        items=[
            RecommendedProduct(
                product_id=p.id,
                slug=p.slug,
                title=p.title,
                kind=_kind_value(p),
                score=1,
                matched_tags=[],
            )
            for p in products
        ],
        country=code,
    )
