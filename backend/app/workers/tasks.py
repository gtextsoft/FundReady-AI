"""Idempotent background job handlers.

Handlers (`run_audit`, `assess_evidence`, ...) must be safe to retry: a repeated
run must not duplicate an AuditRun, re-charge a founder, or double-spend AI
budget (DECISIONS.md D14).

**RQ calls synchronous functions; everything below it is async.** Each handler is
therefore a thin sync entry point around an async body, and the async body is
what tests drive -- `asyncio.run` in the middle of a test is a second event loop
and a source of failures that have nothing to do with the code under test.

**Retry safety here is a state check, not an assumption.** The unique constraint
stops a *second row*; it does nothing about the same row being handed to a second
worker after a timeout. So `run_audit` refuses a run that has already succeeded,
which is the case that costs money: re-running it would re-bill the audit and
could hand the founder a different verdict for identical inputs -- the exact
thing T2.9 asserts cannot happen.
"""

import asyncio
import logging
import sys
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.modules.audit.finance import compute
from app.modules.audit.pipeline import (
    ProfileSnapshot,
    assemble_benchmark_context,
    financial_inputs,
    run_pipeline,
)
from app.modules.audit.repository import AuditRunRepository
from app.modules.audit.runs import AuditStatus
from app.modules.audit.schemas import report_to_storage
from app.modules.audit.synthesis import AuditReport
from app.modules.intake.repository import StartupProfileRepository

logger = logging.getLogger(__name__)

__all__ = ["run_audit", "run_audit_async"]

if sys.platform == "win32":
    # Same reason as `app.main`: psycopg's async mode cannot run on Windows'
    # default ProactorEventLoop. The worker entry point does not import
    # `app.main`, so the policy has to be set where the loop is actually
    # created. A no-op off Windows.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Founder-facing failure reasons. Deliberately short and non-technical: this
# text is read back over the API, and a stack trace or a provider error string
# is both useless to a founder and a disclosure risk (`CLAUDE.md` section 4).
_FAILURE_MESSAGE = (
    "The audit could not be completed. Nothing is wrong with your submission -- "
    "please try again shortly, and contact support if it keeps happening."
)


def run_audit(run_id: str) -> None:
    """RQ entry point. See `run_audit_async` for what actually happens."""
    asyncio.run(run_audit_async(uuid.UUID(run_id)))


async def run_audit_async(run_id: uuid.UUID) -> None:
    """Score one queued AuditRun and store its report.

    The session is opened here rather than passed in because a job has no
    request to borrow one from, and it is committed in two stages on purpose:
    the `running` mark is committed *before* the model calls, so a founder
    polling the status sees the run start rather than sitting on `queued` for a
    minute, and so a worker that dies mid-call leaves evidence it began.

    A failure is recorded on the row and **not** re-raised. Letting it propagate
    would put the job on RQ's failed queue for an automatic retry, and every
    retry of an audit is another billed pass over the same evidence. A failed
    run is retried deliberately -- by the founder resubmitting -- not by the
    transport.
    """
    session_factory = get_session_factory()

    async with session_factory() as session:
        repository = AuditRunRepository(session)
        run = await repository.get(run_id)
        if run is None:
            logger.warning("audit run vanished before the worker reached it")
            return
        if run.status is AuditStatus.SUCCEEDED:
            # Already done. Re-running would re-bill the audit and could return
            # a different verdict for identical inputs.
            logger.info(
                "audit already complete; nothing to do",
                extra={"context": {"attempts": run.attempts}},
            )
            return

        # Read off the row before the session closes: an ORM attribute touched
        # after commit is a lazy load against a connection that is gone.
        owner_id = run.owner_id

        snapshot = await _snapshot_for(session, run.startup_id)
        if snapshot is None:
            await repository.mark_failed(
                run,
                code="profile_missing",
                message=(
                    "The startup profile for this audit could not be found. "
                    "Please check your profile and submit again."
                ),
            )
            await session.commit()
            return

        await repository.mark_running(run)
        benchmark_context = await assemble_benchmark_context(
            session, snapshot, compute(financial_inputs(snapshot))
        )
        await session.commit()

    # The model calls happen outside the session. An audit is minutes of
    # latency; holding a pooled Neon connection open across it would exhaust the
    # pool long before the work finished.
    try:
        report = await _score(snapshot, benchmark_context, owner_id=owner_id)
    except Exception:
        # Broad on purpose: every failure mode below this line -- a refusal, a
        # timeout, a provider outage, a validation mismatch -- has the same
        # correct response, which is to record the run as failed and stop. The
        # detail goes to the log, never to the column.
        logger.exception("audit failed")
        async with session_factory() as session:
            failed = await AuditRunRepository(session).get(run_id)
            if failed is not None:
                await AuditRunRepository(session).mark_failed(
                    failed, code="audit_failed", message=_FAILURE_MESSAGE
                )
                await session.commit()
        return

    async with session_factory() as session:
        repository = AuditRunRepository(session)
        stored = await repository.get(run_id)
        if stored is None:  # pragma: no cover - deleted mid-flight
            logger.warning("audit run deleted while it was being scored")
            return
        await repository.mark_succeeded(stored, report_to_storage(report))
        await session.commit()

    logger.info("audit complete")


async def _snapshot_for(
    session: AsyncSession, startup_id: uuid.UUID
) -> ProfileSnapshot | None:
    """Read the profile this run was fingerprinted against.

    Read fresh rather than carried on the job: the row is the source of truth,
    and a job argument would be a copy taken at enqueue time. If the founder has
    edited the profile since, the fingerprint no longer matches what is scored
    here -- which is why the *next* submission produces a new run rather than
    reusing this one.

    **No ownership check, deliberately.** There is no caller to authorise: the
    run row already named this startup, and it was written by a service call
    that did check (`audit.service.request_audit`). Adding a check here would
    need a `CurrentUser` the worker does not have, and inventing one is how a
    background job ends up running as an implicit superuser.
    """
    profile = await StartupProfileRepository(session).get(startup_id)
    if profile is None:
        return None
    return ProfileSnapshot(
        fields=profile.fields or {},
        name=profile.name,
        sector=profile.sector,
        stage=profile.stage,
        country=profile.country,
        currency=profile.currency,
    )


async def _score(
    snapshot: ProfileSnapshot, benchmark_context: str, *, owner_id: uuid.UUID
) -> AuditReport:
    """Run the pipeline with a freshly built AI client.

    Built here rather than at module import so a worker with no
    `ANTHROPIC_API_KEY` fails on the job it cannot do, with that job marked
    failed, instead of refusing to start at all.
    """
    from app.ai.client import AiClient

    client = AiClient(get_settings())
    return await run_pipeline(
        client,
        snapshot=snapshot,
        benchmark_context=benchmark_context,
        user_id=str(owner_id),
    )
