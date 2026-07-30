"""Audit data access.

Layer: **repository** (ARCHITECTURE.md section 3) -- database access only.
Queries in, models/data out. No business rules, no authorization decisions.

Benchmarks are SACI-wide reference data, not tenant data: there is no owner to
filter by and nothing here to isolate. Who may *write* one is still an
authorization decision and still lives in the service.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.benchmarks import BenchmarkMetric, Stage
from app.modules.audit.models import Benchmark


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
