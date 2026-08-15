"""Seed per-country and global benchmark bands so live audits can leave provisional.

    python scripts/seed_benchmarks.py

Idempotent: a cell that already exists is left alone. Values are curated
starting bands (ratios and months only — no absolute currency), not scraped
figures. Replace them from the admin console as real peer data arrives.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import get_session_factory  # noqa: E402
from app.modules.audit.benchmarks import (  # noqa: E402
    ANY_SECTOR,
    GLOBAL_REGION,
    BenchmarkMetric,
)
from app.modules.audit.repository import BenchmarkRepository  # noqa: E402
from app.modules.intake.fields import Stage  # noqa: E402

AS_OF = date(2026, 1, 1)
SOURCE = "SACI curated starting bands (2026). Replace with cited peer data."

# p25 / p50 / p75 for each metric. Dimensionless or months only.
BANDS: dict[BenchmarkMetric, tuple[str, str, str]] = {
    BenchmarkMetric.GROSS_MARGIN_PERCENT: ("35", "55", "75"),
    BenchmarkMetric.RUNWAY_MONTHS: ("6", "12", "18"),
    BenchmarkMetric.LTV_CAC_RATIO: ("1.5", "3.0", "5.0"),
    BenchmarkMetric.CAC_PAYBACK_MONTHS: ("6", "12", "18"),
    BenchmarkMetric.RUN_RATE_VS_TRAILING_PERCENT: ("90", "110", "140"),
    BenchmarkMetric.REVENUE_CHANGE_3M_PERCENT: ("0", "15", "40"),
    BenchmarkMetric.COSTS_CHANGE_3M_PERCENT: ("-5", "8", "20"),
}

COUNTRIES = ("NG", "AE", "GB", "US")
COUNTRY_STAGES = (Stage.SEED, Stage.SERIES_A)


async def seed() -> int:
    created = 0
    skipped = 0
    factory = get_session_factory()
    async with factory() as session:
        repo = BenchmarkRepository(session)
        cells: list[tuple[str, Stage, str]] = [
            (ANY_SECTOR, stage, GLOBAL_REGION) for stage in Stage
        ]
        for country in COUNTRIES:
            for stage in COUNTRY_STAGES:
                cells.append((ANY_SECTOR, stage, country))

        for sector, stage, region in cells:
            for metric, (p25, p50, p75) in BANDS.items():
                existing = await repo.find(
                    sector=sector, stage=stage, metric=metric, region=region
                )
                if existing is not None:
                    skipped += 1
                    continue
                await repo.create(
                    sector=sector,
                    stage=stage,
                    metric=metric,
                    region=region,
                    p25=Decimal(p25),
                    p50=Decimal(p50),
                    p75=Decimal(p75),
                    source=SOURCE,
                    as_of_date=AS_OF,
                    sample_size=40,
                )
                created += 1
        await session.commit()
    print(f"benchmarks seeded: created={created} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(seed()))
