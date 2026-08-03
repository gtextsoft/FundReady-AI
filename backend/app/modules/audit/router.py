"""Audit HTTP endpoints.

The audit engine: extraction, consistency, finance, rubric scoring, synthesis.

Layer: **router** (ARCHITECTURE.md section 3) -- HTTP only. Validate the request
with `schemas`, call exactly one `service` method, return a response schema.
No business logic, no database access, no LLM calls.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.core.deps import CurrentUserDep, SessionDep
from app.core.errors import ForbiddenError, error_responses
from app.core.security import Role
from app.modules.audit import service
from app.modules.audit.benchmarks import BenchmarkMetric, Stage
from app.modules.audit.reports import (
    AdminReport,
    FounderReport,
    admin_report,
    founder_report,
)
from app.modules.audit.schemas import (
    AuditRunResponse,
    BenchmarkCreate,
    BenchmarkResponse,
    BenchmarkUpdate,
)

router = APIRouter(tags=["audit"])

BENCHMARK_NOTE = (
    "\n\n**SACI admins only.** Benchmarks are the yardstick every verdict is "
    "measured against, so a wrong row is a wrong verdict for every startup "
    "scored against it. They are not visible to founders or investors -- "
    "publishing the set would tell a founder exactly what to claim. Every "
    "write is recorded in the immutable audit log."
)


@router.post(
    "/benchmarks",
    status_code=status.HTTP_201_CREATED,
    response_model=BenchmarkResponse,
    summary="Add a benchmark band",
    description=(
        "Creates one peer-group band, keyed by **sector x stage x metric x "
        "region**.\n\n"
        '`sector` and `region` accept `*` for "any", which is what makes the '
        "lookup fallback chain work: a startup with no sector-specific band "
        "falls back to `*` for its region, then to `*`/`*`.\n\n"
        "`source` and `as_of_date` are required -- a verdict cites its "
        "evidence, and a band with no provenance cannot be cited.\n\n"
        "`409` if a band already exists for that key; `422` if the quartiles "
        "are out of order." + BENCHMARK_NOTE
    ),
    responses=error_responses(401, 403, 409, 422),
)
async def create_benchmark(
    payload: BenchmarkCreate, actor: CurrentUserDep, session: SessionDep
) -> BenchmarkResponse:
    benchmark = await service.create_benchmark(
        session, actor, payload.model_dump(mode="python")
    )
    return BenchmarkResponse.of(benchmark)


@router.get(
    "/benchmarks",
    response_model=list[BenchmarkResponse],
    summary="Browse benchmark bands",
    description=(
        "Filter on any subset of the key. Retired bands are hidden unless "
        "`include_retired` is set." + BENCHMARK_NOTE
    ),
    responses=error_responses(401, 403, 422),
)
async def list_benchmarks(
    actor: CurrentUserDep,
    session: SessionDep,
    sector: Annotated[str | None, Query(max_length=120)] = None,
    stage: Annotated[Stage | None, Query()] = None,
    metric: Annotated[BenchmarkMetric | None, Query()] = None,
    region: Annotated[str | None, Query(max_length=2)] = None,
    include_retired: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[BenchmarkResponse]:
    benchmarks = await service.list_benchmarks(
        session,
        actor,
        sector=sector,
        stage=stage,
        metric=metric,
        region=region,
        include_retired=include_retired,
        limit=limit,
        offset=offset,
    )
    return [BenchmarkResponse.of(benchmark) for benchmark in benchmarks]


@router.get(
    "/benchmarks/{benchmark_id}",
    response_model=BenchmarkResponse,
    summary="Read one benchmark band",
    description="Returns a single band, retired or not." + BENCHMARK_NOTE,
    responses=error_responses(401, 403, 404, 422),
)
async def read_benchmark(
    benchmark_id: uuid.UUID, actor: CurrentUserDep, session: SessionDep
) -> BenchmarkResponse:
    return BenchmarkResponse.of(
        await service.get_benchmark(session, actor, benchmark_id)
    )


@router.patch(
    "/benchmarks/{benchmark_id}",
    response_model=BenchmarkResponse,
    summary="Revise a benchmark band",
    description=(
        "Updates values or provenance. **The key cannot be changed** -- "
        "sector, stage, metric, and region say which cell this is, and moving "
        "them would relocate a band somewhere nobody curated it for. Retire "
        "this one and create the right one instead.\n\n"
        "`422` if the resulting quartiles are out of order." + BENCHMARK_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def update_benchmark(
    benchmark_id: uuid.UUID,
    payload: BenchmarkUpdate,
    actor: CurrentUserDep,
    session: SessionDep,
) -> BenchmarkResponse:
    benchmark = await service.update_benchmark(
        session,
        actor,
        benchmark_id,
        payload.model_dump(exclude_unset=True, mode="python"),
    )
    return BenchmarkResponse.of(benchmark)


@router.post(
    "/benchmarks/{benchmark_id}/retire",
    response_model=BenchmarkResponse,
    summary="Retire a benchmark band",
    description=(
        "Takes a band out of use. **Not a delete**: an AuditRun cites the "
        "benchmark it scored against, so removing the row would strand the "
        "explanation a founder was given. Lookup ignores it immediately."
        + BENCHMARK_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def retire_benchmark(
    benchmark_id: uuid.UUID, actor: CurrentUserDep, session: SessionDep
) -> BenchmarkResponse:
    return BenchmarkResponse.of(
        await service.retire_benchmark(session, actor, benchmark_id)
    )


# ---------------------------------------------------------------------------
# Audit runs (T2.8)
# ---------------------------------------------------------------------------

AUDIT_NOTE = (
    "\n\nAudits run in the background and are **never** performed inline: a "
    "full audit is minutes of model time. Submit, then poll the status "
    "endpoint until `status` is `succeeded` or `failed`."
)


@router.post(
    "/startups/{startup_id}/audits",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AuditRunResponse,
    summary="Request an audit",
    description=(
        "Queues an audit of this startup profile and returns the run to poll.\n\n"
        "**Idempotent on the profile's contents, not on the request.** Submitting "
        "twice without changing anything returns the *same* run -- with `200` "
        "rather than `202` -- because an audit is the most expensive operation "
        "the platform performs and a founder must not be charged twice for one "
        "verdict. Change the profile and the next submission is a new run.\n\n"
        "**Resubmitting a `failed` run is how it is retried.** The run keeps its "
        "id, returns to `queued`, and is re-dispatched -- so a `200` does not "
        "imply nothing was queued. Branch on the returned `status`, not on the "
        "status code. Retries are capped: past the cap the run stays `failed` "
        "with `error_code: audit_retries_exhausted` and submitting again does "
        "nothing.\n\n"
        "`422` when the profile is missing fields the audit needs; the response "
        "`details` carries `missing_fields`, the same list "
        "`GET /v1/startups/me/profile` returns." + AUDIT_NOTE
    ),
    responses={
        200: {
            "model": AuditRunResponse,
            "description": (
                "An audit of these exact inputs already exists, so this run was "
                "not created by this call. It may still have been re-dispatched: "
                "read `status` -- `queued` means a failed run was just retried, "
                "`running` or `succeeded` means no new work was queued."
            ),
        },
        **error_responses(401, 403, 404, 422),
    },
)
async def request_audit(
    startup_id: uuid.UUID,
    actor: CurrentUserDep,
    session: SessionDep,
    response: Response,
) -> AuditRunResponse:
    run, created = await service.request_audit(session, actor, startup_id)
    if not created:
        response.status_code = status.HTTP_200_OK
    return AuditRunResponse.model_validate(run)


@router.get(
    "/startups/{startup_id}/audits",
    response_model=list[AuditRunResponse],
    summary="List audit runs",
    description=(
        "This startup's audit runs, newest first. Status only -- no report "
        "content." + AUDIT_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def list_audit_runs(
    startup_id: uuid.UUID, actor: CurrentUserDep, session: SessionDep
) -> list[AuditRunResponse]:
    runs = await service.list_audit_runs(session, actor, startup_id)
    return [AuditRunResponse.model_validate(run) for run in runs]


@router.get(
    "/startups/{startup_id}/audits/{run_id}",
    response_model=AuditRunResponse,
    summary="Poll one audit run",
    description=(
        "The run's lifecycle status. **This endpoint never returns report "
        "content** -- the report is served by its own per-tier serializer, and "
        "a status poll is reachable long before a report exists.\n\n"
        "A run belonging to another founder returns `404`, not `403`: a `403` "
        "would confirm the id is real." + AUDIT_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def read_audit_run(
    startup_id: uuid.UUID,
    run_id: uuid.UUID,
    actor: CurrentUserDep,
    session: SessionDep,
) -> AuditRunResponse:
    run = await service.get_audit_run(session, actor, startup_id, run_id)
    return AuditRunResponse.model_validate(run)


@router.get(
    "/startups/{startup_id}/audits/{run_id}/report",
    response_model=FounderReport,
    summary="Read your audit report",
    description=(
        "The founder's own report, in full: both verdicts with their reasoning, "
        "the data-integrity score, every finding, and the action plan.\n\n"
        "**`404` until the run has succeeded.** A report does not exist while a "
        "run is `queued`, `running`, or `failed`, and an empty `200` would have "
        "clients rendering a blank verdict as a real one. Poll "
        "`GET .../audits/{run_id}` first.\n\n"
        "**Rendering rules the client must follow.** `insufficient_data` is an "
        "*absence*, not a failure -- it must never be shown as 'not fundable', "
        "because the founder has not been assessed and telling them otherwise "
        "is a false verdict. `provisional` must be labelled as provisional "
        "wherever it appears, never as a plain result; expect it to be the "
        "common case. `score` is `null` whenever the level is "
        "`insufficient_data` and must not be coerced to `0`.\n\n"
        "`unevidenced_dimensions` on each verdict is the list to turn into "
        '"answer these next" -- filling them is what moves a verdict off '
        "`provisional`.\n\n"
        "Another founder's run returns `404`, never `403`."
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def read_audit_report(
    startup_id: uuid.UUID,
    run_id: uuid.UUID,
    actor: CurrentUserDep,
    session: SessionDep,
) -> FounderReport:
    stored = await service.get_audit_report(session, actor, startup_id, run_id)
    return founder_report(stored)


@router.get(
    "/admin/startups/{startup_id}/audits/{run_id}/report",
    response_model=AdminReport,
    summary="Read any audit report in full",
    description=(
        "**SACI admins only.** Everything the run concluded, including the "
        "engineer-facing `detail` on each finding that the founder tier "
        "withholds.\n\n"
        "This is the read behind the brokerage: an investor never reaches a "
        "full report through their own entitlement, only through a SACI reveal "
        "at the meeting. Serving it on a separate admin-only path -- rather "
        "than widening the founder endpoint by role -- keeps the two audiences "
        "in two routes, so a change to one cannot silently widen the other."
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def read_audit_report_as_admin(
    startup_id: uuid.UUID,
    run_id: uuid.UUID,
    actor: CurrentUserDep,
    session: SessionDep,
) -> AdminReport:
    if actor.role is not Role.ADMIN:
        raise ForbiddenError
    stored = await service.get_audit_report(session, actor, startup_id, run_id)
    return admin_report(stored)
