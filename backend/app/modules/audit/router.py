"""Audit HTTP endpoints.

The audit engine: extraction, consistency, finance, rubric scoring, synthesis.

Layer: **router** (ARCHITECTURE.md section 3) -- HTTP only. Validate the request
with `schemas`, call exactly one `service` method, return a response schema.
No business logic, no database access, no LLM calls.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUserDep, SessionDep
from app.core.errors import error_responses
from app.modules.audit import service
from app.modules.audit.benchmarks import BenchmarkMetric, Stage
from app.modules.audit.schemas import (
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
