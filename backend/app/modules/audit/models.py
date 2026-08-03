"""Audit ORM tables.

Layer: **models** (ARCHITECTURE.md section 3) -- SQLAlchemy table definitions
only. Every schema change also requires an Alembic migration under
`migrations/`; the database is never hand-edited.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.audit.benchmarks import BenchmarkMetric, Stage
from app.modules.audit.runs import AuditStatus


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


class AuditRun(Base):
    """One execution of the audit pipeline over one startup profile (T2.8).

    **The unique constraint is the idempotency guarantee, not an optimisation.**
    DECISIONS.md D14 requires a repeated run to be safe, and "safe" here has
    teeth: an audit is the most expensive call the platform makes (`claude-opus-5`
    at high effort against a 16k budget, D16), so a duplicate is a real charge
    to a real founder for a verdict they already have. Keying on
    **startup + input fingerprint + rubric version** means a retry -- from RQ,
    from a double-tapped button, from a worker that died mid-run -- finds this
    row instead of creating a second one.

    The constraint closes the race the queue cannot: an RQ `job_id` stops a
    duplicate only while a job is *in flight*, and the id is released the moment
    it finishes. After that, only the database is still saying no.

    **`rubric_version` is stored, not derived** (D12). A run must stay
    explainable after the rubric moves on; reading today's version to explain
    last month's verdict would silently attribute the wrong criteria to it.

    In the constraint it is **redundant by design, not discriminating**:
    `input_fingerprint` already hashes the rubric version into `input_hash`, so
    a new rubric changes the hash on its own and D12 is enforced there. The
    column stays in the key as insurance -- if the fingerprint's inputs are ever
    changed and the rubric is dropped from the hashed payload, this is what
    stops a v2 audit silently reusing a v1 verdict.

    **No embedding column, deliberately.** The task lists embeddings, but
    Anthropic has no embeddings endpoint and the vector's *dimension* is
    provider-specific (1024, 1536, ...). Committing a dimension here would
    silently pick the provider. `pgvector` is already a declared dependency and
    unused; adding the column is one migration once that call is made.
    """

    __tablename__ = "audit_runs"
    __table_args__ = (
        UniqueConstraint(
            "startup_id",
            "input_hash",
            "rubric_version",
            name="uq_audit_runs_idempotency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    startup_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("startup_profiles.id", ondelete="CASCADE"), index=True
    )
    # Denormalised from the profile so an ownership check on the status endpoint
    # is a column comparison rather than a join. `documents` does the same. The
    # authorisation wall is the check itself (CLAUDE.md section 4); this only
    # keeps it cheap enough that nobody is tempted to skip it.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    status: Mapped[AuditStatus] = mapped_column(
        SAEnum(
            AuditStatus,
            native_enum=False,
            length=16,
            name="audit_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=AuditStatus.QUEUED,
        index=True,
    )

    rubric_version: Mapped[str] = mapped_column(String(20))
    # sha256 hex of the audit's inputs -- see `runs.input_fingerprint`.
    input_hash: Mapped[str] = mapped_column(String(64))

    # The full `synthesis.AuditReport`, serialised. Stored whole because a
    # verdict a founder disputes has to be reconstructable exactly as issued.
    # **Tier filtering happens at the serialiser, never here** (CLAUDE.md
    # section 4): this column holds everything, and no endpoint returns it raw.
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Founder-safe failure reason. The engineer-facing detail goes to logs, not
    # to this column, because it is read back over the API.
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(String(500))

    # How many times a worker has picked this up. A retry increments rather
    # than inserting, which is what makes the retry visible at all.
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        return f"<AuditRun {self.id} {self.status} startup={self.startup_id}>"
