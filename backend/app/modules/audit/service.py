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
from typing import Any, Final

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ConflictError,
    InvalidRequestError,
    NotFoundError,
)
from app.core.ownership import owned_or_404
from app.core.security import CurrentUser, assert_admin
from app.modules.audit.benchmarks import (
    ANY_SECTOR,
    GLOBAL_REGION,
    BenchmarkMetric,
    MatchQuality,
    Stage,
)
from app.modules.audit.models import AuditRun, Benchmark
from app.modules.audit.repository import AuditRunRepository, BenchmarkRepository
from app.modules.audit.rubric import v1
from app.modules.audit.runs import AuditStatus, input_fingerprint, lease_cutoff
from app.modules.identity import service as identity
from app.modules.identity.models import AuditAction
from app.modules.intake import service as intake
from app.modules.readiness import service as readiness
from app.workers.queue import enqueue_audit

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
    """Only SACI writes benchmarks (`AUTH.md` section 5), and only with MFA."""
    assert_admin(actor)


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


# ---------------------------------------------------------------------------
# Audit runs (T2.8)
# ---------------------------------------------------------------------------

# One wording for "no such run" and "not your run" alike. They must be
# indistinguishable or the endpoint becomes an oracle for which ids exist
# (`AUTH.md` section 6).
_RUN_DENIED = "No such audit run."

# How many times a worker may claim one run before resubmitting stops re-queuing
# it. Counted in `AuditRun.attempts`, which only a worker increments, so this
# caps *billed* passes rather than button presses: a submission that never
# reaches a worker costs nothing and does not consume one.
MAX_AUDIT_ATTEMPTS: Final = 3

_RETRIES_EXHAUSTED_CODE: Final = "audit_retries_exhausted"
_REQUEUE_FAILED_CODE: Final = "audit_requeue_failed"

# Founder-facing, like every `error_message`: read back over the API, so it says
# what to do next and nothing an operator would want (`CLAUDE.md` section 4).
_EXHAUSTED_MESSAGE: Final = (
    "This audit has failed several times, so it will not be retried "
    "automatically. Please contact support, or change your profile and submit "
    "again to start a new audit."
)
_REQUEUE_FAILED_MESSAGE: Final = (
    "The audit could not be re-queued. Nothing is wrong with your submission -- "
    "please try again shortly, and contact support if it keeps happening."
)


async def request_audit(
    session: AsyncSession, actor: CurrentUser, startup_id: uuid.UUID
) -> tuple[AuditRun, bool]:
    """Queue an audit of this startup, or hand back the run that already covers it.

    Returns the run and whether this call created it, so the router can answer
    `202` for new work and `200` for a run that already exists.

    **Idempotent by fingerprint, not by button press** (D14). An audit is the
    most expensive call the platform makes, so a repeat submission of unchanged
    inputs must return the existing verdict rather than buy a second one. The
    unique constraint is what actually guarantees that: the pre-check below
    loses a race by design, and the `IntegrityError` is caught rather than
    prevented, because two workers can reach this line between the same two
    instructions.

    **The fingerprint is taken from the persisted JSONB**, which is why the
    profile is loaded here rather than accepted as an argument. A profile that
    has not been through Postgres hashes differently -- `Decimal("42.5000")`
    reads back as `42.5` -- and the two hashes would bill one founder twice.

    Refused with `422` when the profile is missing fields marked
    `required_for_audit`. That is not an invented policy: `intake/fields.py`
    already declares which fields an audit needs, and scoring a profile without
    them spends the audit budget to produce `insufficient_data` -- an answer the
    founder can be given for free, along with the list of what to fill in.
    """
    profile = await intake.get_profile(session, actor, startup_id)

    missing = intake.missing_fields(profile)
    if missing:
        raise InvalidRequestError(
            "This profile is missing information the audit needs. Fill in the "
            "listed fields and submit again.",
            {
                "field": "missing_fields",
                "reason": "incomplete_profile",
                "missing_fields": missing,
            },
        )

    fingerprint = input_fingerprint(
        profile_fields=profile.fields or {},
        # Non-empty since T2.4a: the pipeline reads documents now, so an upload
        # changes the answer and must therefore change the hash. Without this a
        # founder who uploads the financials the first run said were missing
        # gets handed the pre-upload verdict back -- a regression that looks
        # exactly like the idempotency cache working correctly.
        #
        # **Passed evidence is folded in for the identical reason (T3.6).** It
        # is what makes a re-audit mean anything: a founder who worked through
        # their action plan and had the proof graded has changed the evidence
        # the audit reasons over, so the hash has to move or `find_by_fingerprint`
        # hands them back the verdict from before they did the work. The keys
        # are sorted so the order two queries return rows in cannot mint a
        # second run for identical inputs.
        document_keys=sorted(
            [
                *await intake.auditable_storage_keys(session, profile.id),
                *await readiness.passed_evidence_keys(session, profile.id),
            ]
        ),
        rubric_version=v1.RUBRIC_VERSION,
    )

    repository = AuditRunRepository(session)
    existing = await repository.find_by_fingerprint(
        startup_id=profile.id,
        input_hash=fingerprint,
        rubric_version=v1.RUBRIC_VERSION,
    )
    if existing is not None:
        await _requeue_if_retryable(session, existing)
        return existing, False

    try:
        async with session.begin_nested():
            run = await repository.create(
                startup_id=profile.id,
                owner_id=profile.owner_id,
                rubric_version=v1.RUBRIC_VERSION,
                input_hash=fingerprint,
            )
    except IntegrityError:
        # Lost the race -- two instances, or one double-tapped button. The other
        # request created the identical run, which is the outcome wanted, so it
        # is read back rather than failed.
        #
        # **The re-read is guaranteed to find it under READ COMMITTED**, which is
        # what Postgres and SQLAlchemy both default to. A conflicting insert
        # blocks on the unique index until the holder resolves: if it committed
        # we get this `IntegrityError` and the row is already visible to the next
        # statement's snapshot; if it rolled back our own insert succeeded and we
        # are not here at all. There is no ordering in which the winner has
        # thrown this error at us and its row is still invisible.
        #
        # So `None` means the invariant itself is gone -- the constraint was
        # dropped, or the isolation level was raised to REPEATABLE READ, where
        # this branch would need a retry instead. Re-raising is right: a 500 the
        # founder retries beats inventing a run id, and it is loud enough to be
        # noticed.
        raced = await repository.find_by_fingerprint(
            startup_id=profile.id,
            input_hash=fingerprint,
            rubric_version=v1.RUBRIC_VERSION,
        )
        if raced is None:  # pragma: no cover - unreachable under READ COMMITTED
            raise
        await _requeue_if_retryable(session, raced)
        return raced, False

    # **Committed before the job is dispatched, deliberately.** The request's
    # session commits when the handler returns, which is *after* this function
    # -- so enqueueing first opens a race the worker always loses: it looks up
    # a row that no other connection can see yet and concludes the run vanished.
    # `join_transaction_mode="create_savepoint"` keeps this discardable in
    # tests, and the dependency's own commit afterwards is a no-op.
    await session.commit()

    enqueue_audit(run.id)
    logger.info(
        "audit queued",
        extra={"context": {"rubric_version": v1.RUBRIC_VERSION}},
    )
    return run, True


def _is_stranded(run: AuditRun) -> bool:
    """Whether this run is waiting on a worker that is never coming.

    Two shapes, one cause -- a job that no longer exists behind a row that says
    it is in flight:

    * `RUNNING` with a claim older than the lease. RQ killed the worker at its
      own timeout, or the container was redeployed, and neither writes to the
      row.
    * `QUEUED` with `attempts > 0` and a `started_at` older than the lease. The
      `failed -> queued` reset committed and the dispatch was then lost.

    `QUEUED` with `attempts == 0` is **not** stranded and is handled separately:
    no worker has ever claimed it, so there is no lease to have expired and
    `started_at` is NULL.
    """
    if run.started_at is None:
        return False
    if run.status not in (AuditStatus.RUNNING, AuditStatus.QUEUED):
        return False
    return run.started_at < lease_cutoff()


async def _requeue_if_retryable(session: AsyncSession, run: AuditRun) -> None:
    """Re-dispatch a run that no worker will otherwise pick up.

    Two states qualify, for different reasons.

    **`queued` with zero attempts** -- the row committed and then
    `enqueue_audit` raised (Redis down, or `REDIS_URL` unset), so the run sits
    in `queued` forever while every resubmission finds it and returns it
    unchanged. `attempts` is only ever incremented by a worker claiming the run,
    so zero means no worker has seen it. A failure to enqueue *here* needs no
    repair: the row is left exactly as it was, so the next submission tries
    again.

    **`failed`** -- the founder resubmitting is the retry path, and three
    separate places already promise it works: `AuditStatus.FAILED`, the
    founder-facing failure message, and `CLIENTS.md` section 5a. The run keeps
    its id and returns to `queued`.

    **Capped at `MAX_AUDIT_ATTEMPTS`.** An audit is the most expensive call the
    platform makes (D16), and an uncapped retry is a founder holding down submit
    against a provider outage, billed a full `claude-opus-5` pass each time --
    the double-spend D14 exists to prevent. At the cap the run stays `failed`
    with a code that says so, rather than accepting a submission that silently
    does nothing.

    **`running` or `queued` past its lease** -- the two stranded states, now
    closed. A `running` run whose worker was killed or redeployed mid-call keeps
    `completed_at` NULL for ever: RQ releases the `job_id` at its own timeout
    and writes nothing to the row, so every resubmission returned it with `200`,
    queued nothing, and `CLIENTS.md` section 5a told the client to keep polling.
    A `queued` run with `attempts > 0` is the same shape from the other
    direction -- the reset committed and the dispatch was lost.

    The lease is what makes this safe, and it is deliberately **twice** the RQ
    job timeout (`runs.LEASE_SECONDS`). This function still cannot tell a worker
    that died from one that is mid-call; what it can tell is that no honest
    worker is still holding a claim taken half an hour ago, because RQ would
    have killed it at fifteen minutes. Re-dispatching sooner than that would
    bill the platform's most expensive call twice for one verdict.

    Re-dispatch does not re-claim: `repository.claim` is the only thing that
    moves a run into `running`, and it applies the same lease. So a founder
    resubmitting against a genuinely live worker changes nothing.

    Not idempotent-by-transport: RQ does **not** refuse a second job for a
    `job_id` already in flight -- `enqueue` overwrites the hash and re-pushes the
    id -- so the state checks above are the only thing preventing a duplicate
    dispatch. Do not relax them on the assumption that RQ will catch it.

    **Residual window, not closed here.** The reset commits before the dispatch,
    so an `enqueue_audit` that *raises* is caught below and the run is put back
    to `failed`. A process that dies between the commit and the enqueue, or a
    Redis that accepts the job and loses it, is not -- that leaves the row
    `queued` with `attempts > 0`, which is exactly the stranded state the lease
    branch below now repairs.
    """
    if _is_stranded(run):
        # No state change here, deliberately: the row is already in a state a
        # worker can claim, and `repository.claim` applies the same lease. All
        # that is missing is a job, so all this does is put one back. Writing
        # `queued` first would reset nothing useful and would lose the
        # `running` evidence if the dispatch failed again.
        logger.info(
            "re-dispatching a stranded audit run",
            extra={
                "context": {
                    "run_id": str(run.id),
                    "status": run.status.value,
                    "attempts": run.attempts,
                }
            },
        )
        enqueue_audit(run.id)
        return

    if run.status is AuditStatus.FAILED:
        repository = AuditRunRepository(session)
        if run.attempts >= MAX_AUDIT_ATTEMPTS:
            if run.error_code != _RETRIES_EXHAUSTED_CODE:
                await repository.mark_failed(
                    run, code=_RETRIES_EXHAUSTED_CODE, message=_EXHAUSTED_MESSAGE
                )
                await session.commit()
            return

        await repository.mark_queued(run)
        await session.commit()
        try:
            enqueue_audit(run.id)
        except Exception:
            # Committed as `queued` with `attempts > 0` and no job behind it --
            # a state neither branch above can repair, so it would be stranded
            # permanently by the very function that exists to prevent that. Put
            # it back to `failed`, which is somewhere the founder can retry from.
            logger.exception(
                "could not re-queue a failed audit run",
                extra={"context": {"run_id": str(run.id)}},
            )
            await repository.mark_failed(
                run, code=_REQUEUE_FAILED_CODE, message=_REQUEUE_FAILED_MESSAGE
            )
            await session.commit()
        return

    if run.status is AuditStatus.QUEUED and run.attempts == 0:
        enqueue_audit(run.id)


async def get_audit_run(
    session: AsyncSession,
    actor: CurrentUser,
    startup_id: uuid.UUID,
    run_id: uuid.UUID,
) -> AuditRun:
    """One run's status, for its owner or an admin.

    A straight IDOR surface: `run_id` arrives from the client and names a row
    that belongs to exactly one founder. `owned_or_404` settles both "no such
    run" and "not yours" with the same answer, and the `startup_id` in the path
    is checked against the row rather than trusted -- otherwise a caller could
    read their own startup's path with someone else's run id and learn that the
    id is real.
    """
    run = await AuditRunRepository(session).get(run_id)
    if run is not None and run.startup_id != startup_id:
        run = None
    return owned_or_404(run, actor, message=_RUN_DENIED)


async def list_audit_runs(
    session: AsyncSession, actor: CurrentUser, startup_id: uuid.UUID
) -> list[AuditRun]:
    """This startup's runs, newest first. Ownership is checked on the profile."""
    profile = await intake.get_profile(session, actor, startup_id)
    return await AuditRunRepository(session).list_for_startup(profile.id)


async def get_audit_report(
    session: AsyncSession,
    actor: CurrentUser,
    startup_id: uuid.UUID,
    run_id: uuid.UUID,
) -> dict[str, Any]:
    """The stored report document for one run, for its owner or an admin.

    Returns the **whole** stored document. Tier filtering is the router's
    serializer choice (`audit.reports`), not this function's job -- keeping the
    two apart is what lets one service method serve the founder endpoint and the
    SACI reveal without either of them re-deriving ownership.

    Ownership is delegated to `get_audit_run`, so the `startup_id` in the path
    is checked against the row and a run belonging to another founder is `404`
    rather than `403` -- see that function for why.

    A run that has not succeeded has no report. That is `404` and not an empty
    body: the report genuinely does not exist yet, and a `200` carrying nulls
    would have clients rendering an empty verdict as a real one. The message
    points at the status endpoint rather than explaining the lifecycle here.
    """
    run = await get_audit_run(session, actor, startup_id, run_id)

    if run.status is not AuditStatus.SUCCEEDED or run.report is None:
        raise NotFoundError(
            "This audit has no report yet. Poll the audit run until its status "
            "is `succeeded`."
        )

    return run.report
