"""Seed a small set of Benchmark rows for NG / GB / US fintech at seed stage.

    python scripts/seed_benchmarks.py

Idempotent on the natural key (sector, stage, metric, region) — re-running
skips cells that already exist. Refuses to run against production.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_session_factory  # noqa: E402
from app.modules.audit.benchmarks import BenchmarkMetric, Stage  # noqa: E402
from app.modules.audit.repository import BenchmarkRepository  # noqa: E402

SECTOR = "fintech"
STAGE = Stage.SEED
AS_OF = date(2026, 1, 1)
SOURCE = "SACI curated seed set (ops helper)"

# region → metric → (p25, p50, p75)
_BANDS: dict[str, dict[BenchmarkMetric, tuple[str, str, str]]] = {
    "NG": {
        BenchmarkMetric.GROSS_MARGIN_PERCENT: ("35", "55", "70"),
        BenchmarkMetric.RUNWAY_MONTHS: ("6", "12", "18"),
        BenchmarkMetric.LTV_CAC_RATIO: ("1.5", "3.0", "5.0"),
        # Lower is better; band still ordered p25 <= p50 <= p75.
        BenchmarkMetric.CAC_PAYBACK_MONTHS: ("6", "12", "18"),
        BenchmarkMetric.REVENUE_CHANGE_3M_PERCENT: ("5", "15", "30"),
    },
    "GB": {
        BenchmarkMetric.GROSS_MARGIN_PERCENT: ("40", "60", "75"),
        BenchmarkMetric.RUNWAY_MONTHS: ("9", "15", "24"),
        BenchmarkMetric.LTV_CAC_RATIO: ("2.0", "3.5", "6.0"),
        BenchmarkMetric.CAC_PAYBACK_MONTHS: ("5", "10", "15"),
        BenchmarkMetric.REVENUE_CHANGE_3M_PERCENT: ("5", "12", "25"),
    },
    "US": {
        BenchmarkMetric.GROSS_MARGIN_PERCENT: ("45", "65", "80"),
        BenchmarkMetric.RUNWAY_MONTHS: ("12", "18", "24"),
        BenchmarkMetric.LTV_CAC_RATIO: ("2.5", "4.0", "7.0"),
        BenchmarkMetric.CAC_PAYBACK_MONTHS: ("4", "9", "14"),
        BenchmarkMetric.REVENUE_CHANGE_3M_PERCENT: ("8", "18", "35"),
    },
}


async def seed() -> int:
    settings = get_settings()
    if settings.is_production:
        print("refusing to run against production", file=sys.stderr)
        return 2

    async with get_session_factory()() as session:
        repo = BenchmarkRepository(session)
        created = 0
        skipped = 0
        for region, metrics in _BANDS.items():
            for metric, (p25, p50, p75) in metrics.items():
                existing = await repo.find(
                    sector=SECTOR, stage=STAGE, metric=metric, region=region
                )
                if existing is not None:
                    skipped += 1
                    print(f"skip {SECTOR}/{STAGE.value}/{metric.value}/{region}")
                    continue
                await repo.create(
                    sector=SECTOR,
                    stage=STAGE,
                    metric=metric,
                    region=region,
                    p25=Decimal(p25),
                    p50=Decimal(p50),
                    p75=Decimal(p75),
                    source=SOURCE,
                    as_of_date=AS_OF,
                    sample_size=50,
                )
                created += 1
                print(f"created {SECTOR}/{STAGE.value}/{metric.value}/{region}")
        await session.commit()

    print(f"done: {created} created, {skipped} skipped")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(seed()))


if __name__ == "__main__":
    main()
