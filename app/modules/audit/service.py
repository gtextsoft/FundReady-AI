"""Audit business logic.

Layer: **service** (ARCHITECTURE.md section 3) -- business logic and
orchestration. Performs authorization and ownership checks (AUTH.md sections
5-6), calls this module's `repository`, `app.ai`, and other modules' public
service functions only (never their internals). Enqueues background jobs.
Selects the tier serializer for every response carrying report data
(DECISIONS.md D8).

Benchmarks (T2.3) are **SACI reference data, written by admins only**. They are
not tenant data -- there is no owner and nothing to isolate -- but they are the
yardstick every verdict is measured against, so a bad row is a wrong verdict for
every startup it touches. Writes are therefore admin-gated and audit-logged like
any other admin action (`CLAUDE.md` section 4).
"""

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ConflictError,
    ForbiddenError,
    InvalidRequestError,
    NotFoundError,
)
from app.core.security import CurrentUser, Role
from app.modules.audit.benchmarks import (
    ANY_SECTOR,
    GLOBAL_REGION,
    BenchmarkMetric,
    MatchQuality,
    Stage,
)
from app.modules.audit.models import Benchmark
from app.modules.audit.repository import BenchmarkRepository
from app.modules.identity import service as identity
from app.modules.identity.models import AuditAction

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BenchmarkMatch:
    """A benchmark, and how well it actually matched the request.

    The quality travels with the value on purpose. A comparison against an
    all-sectors global median is a far weaker basis for a verdict than a
    Nigerian fintech one, and the rubric's `provisional` status (T2.6,
    `CLAUDE.md` section 5) depends on being able to tell them apart. Returning
    a bare number would produce confident scores off weak comparisons.
    """

    benchmark: Benchmark
    quality: MatchQuality


# What identifies the cell a band belongs to. Changing any of them relocates a
# benchmark to a place nobody curated it for, so they are refused on update
# rather than being quietly applied.
_KEY_FIELDS: frozenset[str] = frozenset({"sector", "stage", "metric", "region"})


def _require_admin(actor: CurrentUser) -> None:
    """Only SACI writes benchmarks (`AUTH.md` section 5)."""
    if actor.role is not Role.ADMIN:
        raise ForbiddenError


def _normalise_sector(sector: str) -> str:
    """Sectors are free text (D11), so they are matched case-insensitively.

    Without this, "Fintech" and "fintech" are two cells and a lookup misses the
    benchmark somebody curated -- silently, because a miss and an absence look
    identical.
    """
    return sector.strip().lower() or ANY_SECTOR


def _normalise_region(region: str) -> str:
    return region.strip().upper() if region.strip() != GLOBAL_REGION else GLOBAL_REGION


# ---------------------------------------------------------------------------
# Lookup -- the reason the table exists
# ---------------------------------------------------------------------------


async def lookup_benchmark(
    session: AsyncSession,
    *,
    sector: str,
    stage: Stage,
    metric: BenchmarkMetric,
    region: str,
) -> BenchmarkMatch | None:
    """The closest stored benchmark, and how close it was.

    **Stage is always matched exactly.** A seed-stage band tells you nothing
    about a growth-stage company -- that is the whole point of keying by stage --
    so widening it would produce a comparison worse than none.

    Sector and region fall back in a fixed order, most specific first:

    1. this sector, this region
    2. this sector, global
    3. any sector, this region
    4. any sector, global

    Sector is free text (D11), so an exact match often misses and the chain is
    the feature rather than an edge case. It is four plain equality queries in a
    stated order rather than one clever query, because an admin has to be able
    to predict which row a startup will be scored against.

    Deliberately **not** fuzzy: no embedding similarity, no nearest-neighbour
    sector match, even though pgvector is available. A curated table with a
    deterministic chain is reviewable and reproducible (D9); a similarity score
    deciding which benchmark a founder is judged by is neither.

    `None` when nothing matches at all -- which the rubric must treat as "no
    comparison available", never as "average".
    """
    repository = BenchmarkRepository(session)
    normalised_sector = _normalise_sector(sector)
    normalised_region = _normalise_region(region)

    attempts: tuple[tuple[str, str, MatchQuality], ...] = (
        (normalised_sector, normalised_region, MatchQuality.EXACT),
        (normalised_sector, GLOBAL_REGION, MatchQuality.REGION_FALLBACK),
        (ANY_SECTOR, normalised_region, MatchQuality.SECTOR_FALLBACK),
        (ANY_SECTOR, GLOBAL_REGION, MatchQuality.BROAD),
    )

    for candidate_sector, candidate_region, quality in attempts:
        found = await repository.find(
            sector=candidate_sector,
            stage=stage,
            metric=metric,
            region=candidate_region,
        )
        if found is not None:
            return BenchmarkMatch(benchmark=found, quality=quality)
    return None


# ---------------------------------------------------------------------------
# Admin CRUD
# ---------------------------------------------------------------------------


def _validate_band(p25: Decimal, p50: Decimal, p75: Decimal) -> None:
    """Quartiles have to be ordered to mean anything.

    A band with p50 below p25 is not a stricter benchmark, it is a typo, and it
    would silently invert every verdict scored against it.
    """
    if not p25 <= p50 <= p75:
        raise InvalidRequestError(
            "Quartiles must be ordered: p25 <= p50 <= p75.",
            {"field": "p50", "reason": "quartiles_out_of_order"},
        )


async def create_benchmark(
    session: AsyncSession, actor: CurrentUser, payload: dict[str, Any]
) -> Benchmark:
    """Add a band. Admin only, and logged."""
    _require_admin(actor)

    sector = _normalise_sector(payload["sector"])
    region = _normalise_region(payload["region"])
    stage: Stage = payload["stage"]
    metric: BenchmarkMetric = payload["metric"]
    p25, p50, p75 = payload["p25"], payload["p50"], payload["p75"]
    _validate_band(p25, p50, p75)

    repository = BenchmarkRepository(session)
    if (
        await repository.find(sector=sector, stage=stage, metric=metric, region=region)
        is not None
    ):
        raise ConflictError("A benchmark already exists for that key.")

    benchmark = await repository.create(
        sector=sector,
        stage=stage,
        metric=metric,
        region=region,
        p25=p25,
        p50=p50,
        p75=p75,
        source=payload["source"],
        as_of_date=payload["as_of_date"],
        sample_size=payload.get("sample_size"),
    )
    await identity.record_action(
        session,
        AuditAction.BENCHMARK_CREATED,
        actor_id=actor.id,
        target_type="benchmark",
        target_id=benchmark.id,
        details={"metric": metric.value, "sector": sector, "region": region},
    )
    return benchmark


async def update_benchmark(
    session: AsyncSession,
    actor: CurrentUser,
    benchmark_id: uuid.UUID,
    payload: dict[str, Any],
) -> Benchmark:
    """Revise a band's values or provenance. Admin only, and logged.

    The **key is immutable**: sector, stage, metric, and region identify which
    cell this is, and editing them would silently move a band somewhere it was
    never curated for. Retire the row and create the right one instead.

    That is enforced *here* rather than left to `BenchmarkUpdate` not declaring
    the fields. The schema stops an HTTP caller, but this is a public service
    function -- T2.6 and any admin tooling reach it with a plain dict, and a
    stated invariant nothing checks is worse than no claim at all.
    """
    _require_admin(actor)

    immutable = _KEY_FIELDS & payload.keys()
    if immutable:
        raise InvalidRequestError(
            "A benchmark's key cannot be changed. Retire this band and create "
            "the one you want instead.",
            {"field": sorted(immutable)[0], "reason": "immutable_key"},
        )

    benchmark = await BenchmarkRepository(session).get(benchmark_id)
    if benchmark is None:
        raise NotFoundError("No such benchmark.")

    p25 = payload.get("p25", benchmark.p25)
    p50 = payload.get("p50", benchmark.p50)
    p75 = payload.get("p75", benchmark.p75)
    _validate_band(p25, p50, p75)

    for field, value in payload.items():
        setattr(benchmark, field, value)
    await session.flush()

    await identity.record_action(
        session,
        AuditAction.BENCHMARK_UPDATED,
        actor_id=actor.id,
        target_type="benchmark",
        target_id=benchmark.id,
        details={"fields": sorted(payload)},
    )
    return benchmark


async def retire_benchmark(
    session: AsyncSession, actor: CurrentUser, benchmark_id: uuid.UUID
) -> Benchmark:
    """Take a band out of use without deleting it. Admin only, and logged.

    Not a delete: an AuditRun cites the benchmark it scored against (T2.8), so
    removing the row would strand the explanation a founder was given. Lookup
    ignores retired rows immediately.
    """
    _require_admin(actor)

    benchmark = await BenchmarkRepository(session).get(benchmark_id)
    if benchmark is None:
        raise NotFoundError("No such benchmark.")

    benchmark.is_active = False
    await session.flush()

    await identity.record_action(
        session,
        AuditAction.BENCHMARK_RETIRED,
        actor_id=actor.id,
        target_type="benchmark",
        target_id=benchmark.id,
    )
    return benchmark


async def list_benchmarks(
    session: AsyncSession,
    actor: CurrentUser,
    *,
    sector: str | None = None,
    stage: Stage | None = None,
    metric: BenchmarkMetric | None = None,
    region: str | None = None,
    include_retired: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[Benchmark]:
    """Browse the knowledge base. Admin only.

    Not founder- or investor-visible: a benchmark is SACI's yardstick and
    publishing the full set would tell a founder exactly what to claim.
    """
    _require_admin(actor)
    return await BenchmarkRepository(session).list_all(
        sector=_normalise_sector(sector) if sector else None,
        stage=stage,
        metric=metric,
        region=_normalise_region(region) if region else None,
        include_retired=include_retired,
        limit=limit,
        offset=offset,
    )


async def get_benchmark(
    session: AsyncSession, actor: CurrentUser, benchmark_id: uuid.UUID
) -> Benchmark:
    """One band by id. Admin only."""
    _require_admin(actor)
    benchmark = await BenchmarkRepository(session).get(benchmark_id)
    if benchmark is None:
        raise NotFoundError("No such benchmark.")
    return benchmark
