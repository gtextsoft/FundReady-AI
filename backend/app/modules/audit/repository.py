"""Audit data access.

Layer: **repository** (ARCHITECTURE.md section 3) -- database access only.
Queries in, models/data out. No business rules, no authorization decisions.

Benchmarks are SACI-wide reference data, not tenant data: there is no owner to
filter by and nothing here to isolate. Who may *write* one is still an
authorization decision and still lives in the service.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.benchmarks import BenchmarkMetric, Stage
from app.modules.audit.models import AuditRun, Benchmark
from app.modules.audit.runs import AuditStatus


class BenchmarkRepository:
    """Read and write benchmark bands."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, benchmark_id: uuid.UUID) -> Benchmark | None:
        return await self._session.get(Benchmark, benchmark_id)

    async def find(
        self,
        *,
        sector: str,
        stage: Stage,
        metric: BenchmarkMetric,
        region: str,
    ) -> Benchmark | None:
        """One exact cell.

        The fallback chain is the service's job; this answers precisely what it
        was asked, which is what makes each rung of that chain testable alone.
        """
        result: Benchmark | None = await self._session.scalar(
            select(Benchmark).where(
                Benchmark.sector == sector,
                Benchmark.stage == stage,
                Benchmark.metric == metric,
                Benchmark.region == region,
                Benchmark.is_active.is_(True),
            )
        )
        return result

    async def list_all(
        self,
        *,
        sector: str | None = None,
        stage: Stage | None = None,
        metric: BenchmarkMetric | None = None,
        region: str | None = None,
        include_retired: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Benchmark]:
        """Browse the knowledge base, filtered on any subset of the key.

        Retired rows are hidden unless asked for: an admin reviewing coverage
        wants what is in force, and retired rows exist to keep past audits
        explainable rather than to be read.
        """
        query: Select[tuple[Benchmark]] = select(Benchmark)
        if sector is not None:
            query = query.where(Benchmark.sector == sector)
        if stage is not None:
            query = query.where(Benchmark.stage == stage)
        if metric is not None:
            query = query.where(Benchmark.metric == metric)
        if region is not None:
            query = query.where(Benchmark.region == region)
        if not include_retired:
            query = query.where(Benchmark.is_active.is_(True))

        query = query.order_by(
            Benchmark.metric, Benchmark.sector, Benchmark.stage, Benchmark.region
        )
        result = await self._session.scalars(query.limit(limit).offset(offset))
        return list(result)

    async def create(
        self,
        *,
        sector: str,
        stage: Stage,
        metric: BenchmarkMetric,
        region: str,
        p25: Decimal,
        p50: Decimal,
        p75: Decimal,
        source: str,
        as_of_date: date,
        sample_size: int | None = None,
    ) -> Benchmark:
        benchmark = Benchmark(
            sector=sector,
            stage=stage,
            metric=metric,
            region=region,
            p25=p25,
            p50=p50,
            p75=p75,
            source=source,
            as_of_date=as_of_date,
            sample_size=sample_size,
        )
        self._session.add(benchmark)
        await self._session.flush()
        return benchmark


class AuditRunRepository:
    """Read and write audit runs.

    Nothing here filters by owner, for the reason the intake repository states:
    ownership is an authorization decision and lives in the service (D13).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, run_id: uuid.UUID) -> AuditRun | None:
        return await self._session.get(AuditRun, run_id)

    async def find_by_fingerprint(
        self, *, startup_id: uuid.UUID, input_hash: str, rubric_version: str
    ) -> AuditRun | None:
        """The existing run for these exact inputs, if there is one.

        The same three columns as `uq_audit_runs_idempotency`. This is the
        cheap path -- the constraint is what actually guarantees uniqueness
        when two requests race, and the service handles that separately.
        """
        result: AuditRun | None = await self._session.scalar(
            select(AuditRun).where(
                AuditRun.startup_id == startup_id,
                AuditRun.input_hash == input_hash,
                AuditRun.rubric_version == rubric_version,
            )
        )
        return result

    async def list_for_startup(
        self, startup_id: uuid.UUID, *, limit: int = 50
    ) -> list[AuditRun]:
        """Newest first -- a founder reading their history wants the last one."""
        result = await self._session.scalars(
            select(AuditRun)
            .where(AuditRun.startup_id == startup_id)
            .order_by(AuditRun.created_at.desc())
            .limit(limit)
        )
        return list(result)

    async def create(
        self,
        *,
        startup_id: uuid.UUID,
        owner_id: uuid.UUID,
        rubric_version: str,
        input_hash: str,
    ) -> AuditRun:
        run = AuditRun(
            startup_id=startup_id,
            owner_id=owner_id,
            rubric_version=rubric_version,
            input_hash=input_hash,
            status=AuditStatus.QUEUED,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def mark_running(self, run: AuditRun) -> AuditRun:
        """Claim the run for this worker attempt.

        `attempts` increments rather than a second row being inserted, which is
        what makes a retry visible at all -- a retried run that looked like a
        first attempt would hide a worker crash loop.
        """
        run.status = AuditStatus.RUNNING
        run.attempts += 1
        run.started_at = datetime.now(UTC)
        run.error_code = None
        run.error_message = None
        await self._session.flush()
        return run

    async def mark_queued(self, run: AuditRun) -> AuditRun:
        """Return a failed run to the queue for another attempt.

        The failure is cleared because the row is once again a run that has not
        finished, and a stale `error_code` beside `status=queued` would be read
        by the client as a run that both failed and is pending.

        **`attempts` is deliberately not reset.** It counts every worker that
        has ever claimed this run, which is what lets the service cap retries on
        it -- resetting would hand a founder an unbounded number of billed
        passes -- and what keeps a crash loop visible, per `mark_running`.
        """
        run.status = AuditStatus.QUEUED
        run.error_code = None
        run.error_message = None
        run.completed_at = None
        await self._session.flush()
        return run

    async def mark_succeeded(self, run: AuditRun, report: dict[str, Any]) -> AuditRun:
        run.status = AuditStatus.SUCCEEDED
        run.report = report
        run.completed_at = datetime.now(UTC)
        await self._session.flush()
        return run

    async def mark_failed(self, run: AuditRun, *, code: str, message: str) -> AuditRun:
        """Record a founder-safe failure.

        `message` is read back over the API, so it carries nothing an operator
        would want and a founder should not see. The engineer-facing detail
        goes to the log line, not to this column.
        """
        run.status = AuditStatus.FAILED
        run.error_code = code
        run.error_message = message[:500]
        run.completed_at = datetime.now(UTC)
        await self._session.flush()
        return run
