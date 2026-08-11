"""Seed the catalogue with the Funding Readiness and Wealth Creation programmes.

    python scripts/seed_products.py

Idempotent on slug — re-running updates title/description/tags for the two
seed programmes without creating duplicates. Refuses to run against production.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_session_factory  # noqa: E402
from app.modules.commerce.models import Product, ProductKind  # noqa: E402
from app.modules.commerce.repository import ProductRepository  # noqa: E402

SEED: tuple[dict[str, object], ...] = (
    {
        "kind": ProductKind.PROGRAM,
        "slug": "funding-readiness-challenge",
        "title": "The Funding Readiness Challenge",
        "description": (
            "For scores below the investor screening floor. Rebuilds the pitch "
            "narrative and forces clarity on unit economics before you burn "
            "warm intros. Six weeks: weekly deck teardown with an operating "
            "partner, CAC/LTV instrumentation clinic, and a free re-score at "
            "week 6."
        ),
        "regions": ["*"],
        "gap_tags": [
            "unit_economics",
            "market_opportunity",
            "team",
            "traction",
        ],
        "stripe_price_id": None,
        "amount_minor": None,
        "currency": None,
        "active": True,
    },
    {
        "kind": ProductKind.PROGRAM,
        "slug": "wealth-creation-challenge",
        "title": "The Wealth Creation Challenge",
        "description": (
            "For companies already clearing the investor screening floor. "
            "Compounding what works and building an investor pipeline you "
            "actually control. Ten weeks: warm routing to matched VC and PE "
            "mandates, scaling playbooks for channel and pricing, and a live "
            "listing in the investor dealflow database."
        ),
        "regions": ["*"],
        "gap_tags": [
            "scalability",
            "go_to_market",
            "fundraising",
            "governance",
        ],
        "stripe_price_id": None,
        "amount_minor": None,
        "currency": None,
        "active": True,
    },
)


async def seed() -> int:
    settings = get_settings()
    if settings.is_production:
        print("refusing to run against production", file=sys.stderr)
        return 2

    async with get_session_factory()() as session:
        products = ProductRepository(session)
        created = 0
        updated = 0
        for row in SEED:
            slug = str(row["slug"])
            existing = await products.get_by_slug(slug)
            if existing is None:
                await products.add(
                    Product(
                        kind=row["kind"],  # type: ignore[arg-type]
                        slug=slug,
                        title=str(row["title"]),
                        description=str(row["description"]),
                        regions=list(row["regions"]),  # type: ignore[arg-type]
                        gap_tags=list(row["gap_tags"]),  # type: ignore[arg-type]
                        stripe_price_id=row["stripe_price_id"],  # type: ignore[arg-type]
                        amount_minor=row["amount_minor"],  # type: ignore[arg-type]
                        currency=row["currency"],  # type: ignore[arg-type]
                        active=bool(row["active"]),
                    )
                )
                created += 1
                print(f"created {slug}")
            else:
                existing.title = str(row["title"])
                existing.description = str(row["description"])
                existing.regions = list(row["regions"])  # type: ignore[assignment]
                existing.gap_tags = list(row["gap_tags"])  # type: ignore[assignment]
                existing.active = bool(row["active"])
                updated += 1
                print(f"updated {slug}")
        await session.commit()

    print(f"done: {created} created, {updated} updated")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(seed()))


if __name__ == "__main__":
    main()
