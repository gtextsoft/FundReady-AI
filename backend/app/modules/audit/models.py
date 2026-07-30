"""Audit ORM tables.

Layer: **models** (ARCHITECTURE.md section 3) -- SQLAlchemy table definitions
only. Every schema change also requires an Alembic migration under
`migrations/`; the database is never hand-edited.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.audit.benchmarks import BenchmarkMetric, Stage


class Benchmark(Base):
    """One peer-group band for one metric (T2.3).

    Keyed by **sector x stage x metric x region**, which is what the PRD says
    benchmark lookup is keyed by. `sector` and `region` accept the wildcards in
    `benchmarks.py`, so a row can deliberately be "all sectors, globally" and
    serve as the last rung of the fallback chain.

    **Quartiles, not a single median.** A rubric asking "is this good" needs a
    band, not a point: 40% gross margin is excellent in logistics and poor in
    software, and only a spread says which. Adding p25/p75 later would be a
    migration on a table that already holds curated rows.

    **`source` and `as_of_date` are required.** `CLAUDE.md` section 5 forbids a
    verdict without citable evidence, and a benchmark with no provenance cannot
    be cited -- a founder told their margin is bottom-quartile is entitled to
    know against what, gathered when. Benchmarks also go stale, and a date is
    what makes that visible rather than silent.

    SACI curates these by hand. There is no scraper and no model-generated row:
    a benchmark is the yardstick every verdict is measured against, so an
    invented one is a wrong verdict for every startup it touches.
    """

    __tablename__ = "benchmarks"
    __table_args__ = (
        # One band per cell. Two rows for the same key would let lookup order
        # decide a verdict, which is the non-determinism D9 forbids.
        UniqueConstraint(
            "sector", "stage", "metric", "region", name="uq_benchmarks_key"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # Free text, matching the profile: D11 requires accepting sectors that do
    # not exist yet, so this cannot be an enum. `*` means "any sector".
    sector: Mapped[str] = mapped_column(String(120), index=True)
    stage: Mapped[Stage] = mapped_column(
        SAEnum(
            Stage,
            native_enum=False,
            length=16,
            name="startup_stage",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        index=True,
    )
    metric: Mapped[BenchmarkMetric] = mapped_column(
        SAEnum(
            BenchmarkMetric,
            native_enum=False,
            length=40,
            name="benchmark_metric",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        index=True,
    )
    # ISO 3166-1 alpha-2, matching `startup_profiles.country`, or `*` for
    # global. Two characters is enough for both.
    region: Mapped[str] = mapped_column(String(2), index=True)

    # Numeric, not float: these are compared against `finance.py`'s Decimals,
    # and a float round-trip would let the same input score differently (T2.9).
    p25: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    p50: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    p75: Mapped[Decimal] = mapped_column(Numeric(18, 4))

    sample_size: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(300))
    as_of_date: Mapped[date] = mapped_column(Date)

    # Retired rather than deleted: an AuditRun cites the benchmark it scored
    # against (T2.8), so removing a row would strand past explanations. Lookup
    # reads only active rows.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        return f"<Benchmark {self.metric} {self.sector}/{self.stage}/{self.region}>"
