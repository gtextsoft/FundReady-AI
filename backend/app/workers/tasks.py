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
from app.core.storage import get_object
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
from app.modules.audit.reports import founder_report
from app.modules.audit.repository import AuditRunRepository
from app.modules.audit.schemas import report_to_storage
from app.modules.audit.synthesis import AuditReport
from app.modules.identity.repository import UserRepository
from app.modules.intake import service as intake
from app.modules.intake.documents import DocumentPayload
from app.modules.intake.repository import StartupProfileRepository
from app.modules.notifications import service as notifications
from app.modules.readiness import service as readiness
from app.modules.readiness.assessment import assess_evidence as assess_submissions
from app.modules.readiness.evidence import MAX_ASSESSMENT_ATTEMPTS
from app.modules.readiness.repository import (
    EvidenceRepository,
    ReadinessTaskRepository,
)

if TYPE_CHECKING:
    from app.ai.client import AiClient, AiResult
    from app.modules.readiness.assessment import EvidenceAssessment

logger = logging.getLogger(__name__)

# Used when `APP_LINK_BASE_URL` is unset. A report email with a dead link is
# still worth sending -- the report is in the body -- but the link should not
# render as an empty href.
PRODUCT_URL_FALLBACK = "https://fundready.app"

__all__ = [
    "assess_evidence",
    "assess_evidence_async",
    "run_audit",
    "run_audit_async",
    "send_email",
]


def send_email(to: str, subject: str, html: str, text: str) -> bool:
    """RQ entry point for queued transactional email."""
    from app.modules.notifications.service import send_email as send_inline
    from app.modules.notifications.templates import EmailContent

    return asyncio.run(
        send_inline(to, EmailContent(subject=subject, html=html, text=text))
    )

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
            #
            # **Documents and passed evidence, together (T3.6).** A founder's
            # proof that they closed a gap is evidence about the business in
            # exactly the sense the rubric means, so the re-audit reads it
            # alongside the deck. `request_audit` already folded these keys into
            # the fingerprint, so the run that reaches here is one minted
            # *because* the evidence changed.
            payloads, unfetchable = await intake.load_auditable_documents(
                session, run.startup_id
            )
            evidence, evidence_unfetchable = await readiness.load_passed_evidence(
                session, run.startup_id
            )
            payloads = [*payloads, *evidence]
            unfetchable = [*unfetchable, *evidence_unfetchable]
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
        # Read off the row before the commit closes the session, for the same
        # reason `owner_id` is read early above.
        startup_id = stored.startup_id
        owner_id = stored.owner_id
        await session.commit()

    # **The report is committed before tasks are generated, and generation
    # cannot fail this job (T3.1).** An earlier draft did both in one
    # transaction, reasoning that a report whose action plan reached no task is
    # a founder told "not yet" with nothing to do about it. That was the wrong
    # trade, for a reason this block's position makes structural: everything
    # from here down is **outside the `try` above**, so a raise from generation
    # propagated straight out of `run_audit_async` onto RQ's failed queue for an
    # automatic retry -- and every retry of an audit is another billed
    # `claude-opus-5` high-effort pass. Sharing the transaction made it worse
    # still: the rollback took `mark_succeeded` with it, discarding a report
    # that had already been paid for and stranding the run in `running` for the
    # lease to recover half an hour later. That is the exact three-bug cluster
    # the lease was added to close, reintroduced through a new door.
    #
    # So the expensive, irreplaceable artefact is committed on its own, and
    # generation is best-effort in a transaction of its own.
    await _generate_readiness_tasks(
        run_id, startup_id=startup_id, owner_id=owner_id, report=report
    )

    # Last, and for the same reason task generation is late and best-effort:
    # everything from `mark_succeeded` down is outside the `try`, so a raise
    # here would land the job on RQ's failed queue and buy a second billed
    # `claude-opus-5` pass over evidence that has already been scored.
    await _email_report(run_id, owner_id=owner_id, report=report)

    logger.info("audit complete", extra={"context": {"run_id": str(run_id)}})


async def _email_report(
    run_id: uuid.UUID, *, owner_id: uuid.UUID, report: AuditReport
) -> None:
    """Send the finished report to the founder, and never fail the job doing it.

    The address is looked up here rather than carried down from the top: it is
    read once, at the moment it is needed, so the job holds no PII across the
    minutes of model latency in between.

    What a failure costs: the founder has their report in the app and no email
    about it. That is a strictly better outcome than re-running the audit, which
    is what letting this raise would do.
    """
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            owner = await UserRepository(session).get_by_id(owner_id)
            if owner is None:  # pragma: no cover - deleted mid-flight
                return
            address = owner.email

        settings = get_settings()
        await notifications.send_audit_report_email(
            address,
            founder_report(report_to_storage(report)),
            settings.app_link_base_url.rstrip("/") or PRODUCT_URL_FALLBACK,
            settings=settings,
        )
    except Exception:
        # Deliberately broad, exactly like `_record_failure` and task
        # generation. The address is never logged -- `CLAUDE.md` section 4.
        logger.exception(
            "could not email the audit report",
            extra={"context": {"run_id": str(run_id)}},
        )


async def _generate_readiness_tasks(
    run_id: uuid.UUID,
    *,
    startup_id: uuid.UUID,
    owner_id: uuid.UUID,
    report: AuditReport,
) -> None:
    """Turn the action plan into readiness tasks, and never fail the job doing it.

    Modelled on `_record_failure`, and swallowing for the same reason: this runs
    after the point where the audit has been paid for and stored, so no failure
    here is worth re-running the model over. `CLAUDE.md` section 5 puts audits on
    the queue as idempotent jobs precisely so a retry is cheap; a retry of *this*
    is not, because the retry re-enters at the top.

    **This is the composition root for readiness**, the role `_score` plays for
    extraction: `audit` never learns what a `ReadinessTask` is, and `readiness`
    reads the typed report rather than re-parsing the JSONB just written from it.

    What a failure costs, stated plainly: the founder has their report and an
    empty task list. The next audit that succeeds for this startup regenerates
    the whole plan, because generation reconciles rather than appends -- but
    `request_audit` is idempotent on the profile fingerprint, so an *unchanged*
    profile will not produce a new run. Recovery therefore needs the founder to
    change something, or an operator to notice. The log line is at exception
    level so Sentry raises it rather than leaving it to be discovered.

    One failure is expected rather than exceptional: two runs for the same
    startup finishing concurrently both read no existing tasks and both insert
    the same fingerprints, and `uq_readiness_tasks_action` rejects the loser.
    Not reachable on today's single-worker deploy, and cheap when it becomes
    reachable -- the winner's tasks are already correct and the loser's plan
    covers the same gaps.
    """
    try:
        async with get_session_factory()() as session:
            await readiness.generate_for_report(
                session,
                startup_id=startup_id,
                owner_id=owner_id,
                audit_run_id=run_id,
                report=report,
            )
            await session.commit()
    except Exception:
        logger.exception(
            "readiness tasks could not be generated; the report is stored and "
            "the founder has no action list",
            extra={"context": {"run_id": str(run_id), "startup_id": str(startup_id)}},
        )


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


def assess_evidence(task_id: str) -> None:
    """RQ entry point. See `assess_evidence_async` for what actually happens."""
    asyncio.run(assess_evidence_async(uuid.UUID(task_id)))


async def assess_evidence_async(task_id: uuid.UUID) -> None:
    """Grade one task's outstanding evidence and record the verdict (T3.5).

    Same shape as `run_audit_async` and for the same reasons, but the guarantees
    it needs are not identical, so the differences are worth stating:

    * **Idempotence comes from the query, not from a lease.** `list_gradable`
      returns only `ready` submissions with no `outcome` yet, so a redelivered
      job finds nothing and returns without spending anything. An audit needed a
      conditional UPDATE because its row is claimable in several states; here
      "already graded" is written on the rows themselves, and a second delivery
      simply reads an empty list. Nothing to race over.
    * **A failure is recorded and not re-raised**, exactly as the audit does.
      Letting it propagate puts the job on RQ's failed queue for an automatic
      retry, and every retry is another billed `AUDIT`-tier pass over the same
      files. `record_assessment_failure` returns the task to `open` and charges
      no attempt, because a provider outage is not the founder's mistake.
    * **The attempt is charged on the grading, never on the dispatch.** A job
      that dies before the model answers must leave the counter untouched, or a
      worker restart would silently spend a founder's three tries.

    The model call happens **outside** any session, as in `run_audit_async`: a
    grading is seconds to a minute of latency and holding a pooled Neon
    connection across it exhausts the pool long before the work finishes.
    """
    session_factory = get_session_factory()
    graded: list[uuid.UUID] = []

    try:
        async with session_factory() as session:
            task = await ReadinessTaskRepository(session).get(task_id)
            if task is None:
                logger.warning(
                    "task vanished before its evidence could be graded",
                    extra={"context": {"task_id": str(task_id)}},
                )
                return

            # **Backstop on the attempt cap.** The service refuses a completion
            # past the ceiling, so reaching here means a job was queued before
            # the counter moved -- a redelivery, or two completions racing. This
            # is the last point before money is spent, so it is checked again
            # rather than trusted: a cap enforced only at the HTTP boundary is a
            # cap that a queue reordering can step around.
            if task.assessment_attempts >= MAX_ASSESSMENT_ATTEMPTS:
                logger.warning(
                    "refusing to grade past the attempt cap",
                    extra={
                        "context": {
                            "task_id": str(task_id),
                            "attempts": task.assessment_attempts,
                        }
                    },
                )
                return

            pending = await EvidenceRepository(session).list_gradable(task_id)
            if not pending:
                logger.info(
                    "no evidence outstanding; another delivery already graded it",
                    extra={"context": {"task_id": str(task_id)}},
                )
                return

            # Read everything off the rows before the session closes: an ORM
            # attribute touched afterwards is a lazy load against a connection
            # that is gone.
            criterion = task.action
            owner_id = task.owner_id
            graded = [row.id for row in pending]
            keys = [
                (row.id, row.storage_key, row.filename, row.content_type)
                for row in pending
            ]
            await session.commit()

        submissions = _evidence_sources(keys)
        result = await _grade(
            criterion=criterion, submissions=submissions, owner_id=owner_id
        )
    except Exception:
        # Broad on purpose, and for the same reason as the audit's: every
        # failure mode here -- a refusal, a timeout, an outage, a validation
        # mismatch, a storage blip -- has the same correct response, which is to
        # release the task and stop. The detail goes to the log, never to a
        # column a founder reads.
        logger.exception(
            "evidence assessment failed",
            extra={"context": {"task_id": str(task_id)}},
        )
        await _release_task(task_id, graded)
        return

    async with session_factory() as session:
        await readiness.record_assessment(
            session,
            task_id=task_id,
            graded=graded,
            outcome=result.output.outcome,
            reasons=result.output.reasons,
            prompt_ref=result.record.prompt_ref,
        )
        await session.commit()


def _evidence_sources(
    keys: Sequence[tuple[uuid.UUID, str, str, str | None]],
) -> list[SourceDocument]:
    """Fetch each submission's bytes from the evidence bucket.

    A file that cannot be fetched is **skipped rather than fatal**, mirroring
    `_with_extracted_fields`: one unreadable attachment should cost that
    attachment, not the whole grading. If every one fails the list comes back
    empty and `assess_evidence` returns `needs_more` without spending a call,
    which is the honest answer -- there was nothing to grade.
    """
    sources: list[SourceDocument] = []
    for evidence_id, key, filename, content_type in keys:
        try:
            content = get_object(key, bucket="evidence")
        except Exception:
            logger.exception(
                "an evidence file could not be fetched; grading without it",
                extra={"context": {"evidence_id": str(evidence_id)}},
            )
            continue
        if content is None:
            continue
        sources.append(
            SourceDocument(
                document_id=str(evidence_id),
                filename=filename,
                content_type=content_type or "application/octet-stream",
                content=content,
            )
        )
    return sources


async def _grade(
    *,
    criterion: str,
    submissions: Sequence[SourceDocument],
    owner_id: uuid.UUID,
) -> "AiResult[EvidenceAssessment]":
    """Build a client and grade. Split out so tests can drive it directly.

    The client is constructed here rather than at module import for the reason
    `_score` gives: a worker with no `ANTHROPIC_API_KEY` should fail the job it
    cannot do, with that job recorded, rather than refusing to start at all.
    """
    from app.ai.client import AiClient

    return await assess_submissions(
        AiClient(get_settings()),
        criterion=criterion,
        submissions=submissions,
        user_id=str(owner_id),
    )


async def _release_task(task_id: uuid.UUID, graded: Sequence[uuid.UUID]) -> None:
    """Return a task to `open` after a failed grading, and do not raise doing it.

    Runs inside the `except` above, so the failure it is recording may well *be*
    the database. An exception raised from an `except` block propagates out onto
    RQ's failed queue for the automatic retry this handler exists to avoid --
    same reasoning, and same best-effort shape, as `_record_failure`.
    """
    try:
        async with get_session_factory()() as session:
            await readiness.record_assessment_failure(
                session, task_id=task_id, graded=graded
            )
            await session.commit()
    except Exception:
        logger.exception(
            "could not release a task after a failed assessment",
            extra={"context": {"task_id": str(task_id)}},
        )
