"""Idempotent background job handlers.

Handlers (`run_audit`, `assess_evidence`, ...) must be safe to retry: a repeated
run must not duplicate an AuditRun, re-charge a founder, or double-spend AI
budget (DECISIONS.md D14).

**RQ calls synchronous functions; everything below it is async.** Each handler is
therefore a thin sync entry point around an async body, and the async body is
what tests drive -- `asyncio.run` in the middle of a test is a second event loop
and a source of failures that have nothing to do with the code under test.

**Retry safety here is an atomic claim, not a state check.** The unique
constraint stops a *second row*; it does nothing about the same row being handed
to a second worker after a timeout, and RQ does not dedupe by `job_id`. So
`run_audit` opens with `repository.claim`, a single conditional UPDATE that
exactly one of two concurrent deliveries can win. It used to read the row, check
it was not `succeeded`, and then mark it running -- three statements with two
gaps, either of which let both workers through to bill a `claude-opus-5`
high-effort pass for one verdict, the second overwriting the first report. That
is the "different verdict for identical inputs" T2.9 asserts cannot happen.
"""

import asyncio
import logging
import sys
import uuid
from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.modules.audit.extraction import (
    SourceDocument,
    extract_fields,
    fenced_documents,
    merge_into_profile,
)
from app.modules.audit.finance import compute
from app.modules.audit.pipeline import (
    ProfileSnapshot,
    assemble_benchmark_context,
    financial_inputs,
    render_profile_facts,
    run_pipeline,
)
from app.modules.audit.repository import AuditRunRepository
from app.modules.audit.schemas import report_to_storage
from app.modules.audit.synthesis import AuditReport
from app.modules.intake import service as intake
from app.modules.intake.documents import DocumentPayload
from app.modules.intake.repository import StartupProfileRepository

if TYPE_CHECKING:
    from app.ai.client import AiClient

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

    # **Everything that can fail is inside one `try`, including the database
    # work before the model calls.** It used to wrap `_score` alone, which left
    # `_snapshot_for`, `financial_inputs`, `compute`, and
    # `assemble_benchmark_context` outside it -- and a raise from any of them
    # was worse than an uncaught error. Those run between `mark_running` and its
    # `commit`, so the session unwound without committing and took the `running`
    # mark and the `attempts` increment with it: the row returned to `queued`
    # with zero attempts, the exception went to RQ's failed queue, and the
    # founder saw `queued` with no error. Resubmitting then matched
    # `service._requeue_if_retryable`'s stranded-run branch and dispatched the
    # same failure again, unbounded, with `error_code` never written.
    try:
        async with session_factory() as session:
            repository = AuditRunRepository(session)
            # **Claim before reading anything else.** One conditional UPDATE,
            # so two concurrent deliveries of the same job cannot both proceed:
            # Postgres serialises them on the row and the loser sees no rows
            # matched. The previous shape -- load the row, check it is not
            # `succeeded`, then mark it running -- left a gap between the check
            # and the write in which both workers passed, both ran the pipeline,
            # and the platform paid for two `claude-opus-5` high-effort passes
            # to produce one verdict. RQ does not dedupe by `job_id`, so nothing
            # upstream closed it either.
            if not await repository.claim(run_id):
                logger.info(
                    "audit not claimable; another worker holds it or it is done",
                    extra={"context": {"run_id": str(run_id)}},
                )
                return
            await session.commit()

            run = await repository.get(run_id)
            if run is None:
                logger.warning(
                    "audit run vanished before the worker reached it",
                    extra={"context": {"run_id": str(run_id)}},
                )
                return

            # Read off the row before the session closes: an ORM attribute
            # touched after commit is a lazy load against a connection that is
            # gone.
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

            # Fetched inside the session and before it closes, for the same
            # reason the snapshot is: the bytes have to outlive the connection.
            payloads, unfetchable = await intake.load_auditable_documents(
                session, run.startup_id
            )
            benchmark_context = await assemble_benchmark_context(
                session, snapshot, compute(financial_inputs(snapshot))
            )
            await session.commit()

        # The model calls happen outside the session. An audit is minutes of
        # latency; holding a pooled Neon connection open across it would exhaust
        # the pool long before the work finished.
        report = await _score(
            snapshot,
            benchmark_context,
            owner_id=owner_id,
            payloads=payloads,
            unfetchable=unfetchable,
        )
    except Exception:
        # Broad on purpose: every failure mode above -- a refusal, a timeout, a
        # provider outage, a validation mismatch, a database blip -- has the
        # same correct response, which is to record the run as failed and stop.
        # The detail goes to the log, never to the column.
        logger.exception("audit failed", extra={"context": {"run_id": str(run_id)}})
        await _record_failure(run_id)
        return

    async with session_factory() as session:
        repository = AuditRunRepository(session)
        stored = await repository.get(run_id)
        if stored is None:  # pragma: no cover - deleted mid-flight
            logger.warning(
                "audit run deleted while it was being scored",
                extra={"context": {"run_id": str(run_id)}},
            )
            return
        await repository.mark_succeeded(stored, report_to_storage(report))
        await session.commit()

    logger.info("audit complete", extra={"context": {"run_id": str(run_id)}})


async def _record_failure(run_id: uuid.UUID) -> None:
    """Mark a run failed, and do not raise while doing it.

    This runs inside the `except` above, and the failure it is recording may
    well *be* the database -- in which case opening a session and re-reading the
    row fails too. An exception raised from an `except` block propagates out of
    `run_audit_async` and onto RQ's failed queue for an automatic retry, which
    is the one thing this handler's docstring promises never happens and every
    retry of an audit is another billed pass. So the recording is best-effort:
    if it cannot be written, that is logged and the job still ends cleanly.

    `get_session_factory` is resolved on call rather than passed in, so a test
    that patches it on this module reaches here too.
    """
    try:
        async with get_session_factory()() as session:
            repository = AuditRunRepository(session)
            run = await repository.get(run_id)
            if run is None:
                return
            await repository.mark_failed(
                run, code="audit_failed", message=_FAILURE_MESSAGE
            )
            await session.commit()
    except Exception:
        logger.exception(
            "could not record an audit failure",
            extra={"context": {"run_id": str(run_id)}},
        )


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
    snapshot: ProfileSnapshot,
    benchmark_context: str,
    *,
    owner_id: uuid.UUID,
    payloads: Sequence[DocumentPayload] = (),
    unfetchable: Sequence[str] = (),
) -> AuditReport:
    """Stage 1 (extraction) and then stages 2-5, with a freshly built AI client.

    The client is built here rather than at module import so a worker with no
    `ANTHROPIC_API_KEY` fails on the job it cannot do, with that job marked
    failed, instead of refusing to start at all.

    **This is the composition root for T2.4a.** `audit` never learns what an
    `intake.Document` is and `intake` never learns what a `SourceDocument` is;
    the mapping happens here, which is the only place allowed to know both
    (`ARCHITECTURE.md` section 3) -- the same role `app.main` plays for the user
    loader.
    """
    from app.ai.client import AiClient

    client = AiClient(get_settings())

    sources = [
        SourceDocument(
            document_id=payload.document_id,
            filename=payload.filename,
            content_type=payload.content_type,
            content=payload.content,
        )
        for payload in payloads
    ]

    scored_snapshot = snapshot
    if sources:
        scored_snapshot = await _with_extracted_fields(
            client, snapshot, sources, owner_id=owner_id, unfetchable=unfetchable
        )

    # Only the text-renderable documents reach scoring and contradiction
    # detection; both inline `UntrustedContent.text` and neither can carry a
    # native PDF block. A PDF's content still reaches them, through the fields
    # extraction read out of it -- see `extraction.fenced_documents`.
    fenced, _ = fenced_documents(sources)

    return await run_pipeline(
        client,
        snapshot=scored_snapshot,
        documents=fenced,
        benchmark_context=benchmark_context,
        user_id=str(owner_id),
    )


async def _with_extracted_fields(
    client: "AiClient",
    snapshot: ProfileSnapshot,
    sources: Sequence[SourceDocument],
    *,
    owner_id: uuid.UUID,
    unfetchable: Sequence[str] = (),
) -> ProfileSnapshot:
    """Read the documents and fold what they state into the profile -- in memory.

    **Nothing is written back to `StartupProfile.fields`, deliberately.** The
    idempotency fingerprint is taken from that JSONB, so persisting extracted
    values would move the hash after every run: the next identical submission
    would miss the unique key, mint a fresh AuditRun, and bill a second
    `claude-opus-5` pass for evidence already scored. It is also not
    self-correcting -- extraction runs again, merges again, and the hash moves
    again -- and `merge_into_profile` dropping a low-confidence value on one run
    but keeping it on the next makes it non-convergent. The founder's profile
    stays exactly what they typed; the audit sees the enriched view.

    Persisting the enrichment is worth doing, and it needs the fingerprint taken
    before extraction rather than after. Recorded in `TASKS.md` as its own step.

    An extraction failure is **not** fatal. The documents still reach scoring as
    fenced text and the profile is still scoreable, so a refusal or a timeout
    here costs evidence rather than the whole audit -- and the alternative is
    telling a founder their audit failed when most of it could have run.
    """
    try:
        extracted = await extract_fields(
            client,
            documents=sources,
            known_facts=render_profile_facts(snapshot),
            user_id=str(owner_id),
        )
    except Exception:
        logger.exception(
            "extraction failed; scoring the profile as submitted",
            extra={"context": {"documents": len(sources)}},
        )
        return snapshot

    unreadable = list(dict.fromkeys([*unfetchable, *extracted.output.unreadable]))
    if unreadable:
        logger.info(
            "documents could not be read",
            extra={"context": {"document_ids": unreadable}},
        )

    return replace(
        snapshot,
        fields=merge_into_profile(dict(snapshot.fields), extracted.output),
    )
