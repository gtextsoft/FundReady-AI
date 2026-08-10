"""Readiness business logic.

Layer: **service** (ARCHITECTURE.md section 3) -- business logic and
orchestration. Performs authorization and ownership checks (AUTH.md sections
5-6), calls this module's `repository`, `app.ai`, and other modules' public
service functions only (never their internals). Enqueues background jobs.
Selects the tier serializer for every response carrying report data
(DECISIONS.md D8).
"""

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ConflictError,
    InvalidRequestError,
    NotFoundError,
)
from app.core.ownership import owned_or_404
from app.core.security import CurrentUser, assert_admin
from app.core.storage import (
    StoredObject,
    delete_object,
    get_object,
    head_object,
    object_key,
    signed_download_url,
    signed_upload_url,
)
from app.modules.audit.repository import AuditRunRepository
from app.modules.audit.synthesis import AuditReport
from app.modules.identity import service as identity
from app.modules.identity.models import AuditAction
from app.modules.intake import service as intake
from app.modules.intake.documents import DocumentPayload
from app.modules.intake.service import safe_filename
from app.modules.readiness.evidence import (
    MAX_ASSESSMENT_ATTEMPTS,
    MAX_UPLOAD_BYTES,
    AssessmentOutcome,
    EvidenceStatus,
    is_allowed_content_type,
)
from app.modules.readiness.generation import (
    UNTOUCHED_STATUSES,
    GeneratedTask,
    Requirement,
    TaskStatus,
    plan_for_report,
    required_count,
)
from app.modules.readiness.models import Evidence, ReadinessTask
from app.modules.readiness.repository import (
    EvidenceRepository,
    ReadinessTaskRepository,
)
from app.modules.readiness.schemas import ReadinessSummary
from app.workers.queue import enqueue_assessment

logger = logging.getLogger(__name__)

__all__ = [
    "complete_evidence_upload",
    "load_passed_evidence",
    "passed_evidence_keys",
    "evidence_download_url",
    "generate_for_report",
    "get_evidence",
    "get_task",
    "get_task_by_id",
    "list_evidence",
    "list_tasks",
    "record_assessment",
    "record_assessment_failure",
    "reopen_task",
    "request_evidence_upload",
    "summarise_tasks",
]

_TASK_DENIED = "No such task."


async def generate_for_report(
    session: AsyncSession,
    *,
    startup_id: uuid.UUID,
    owner_id: uuid.UUID,
    audit_run_id: uuid.UUID,
    report: AuditReport,
) -> tuple[ReadinessTask, ...]:
    """Reconcile this startup's tasks against what the audit now asks for.

    **No `CurrentUser`, deliberately.** This is called by the worker, which has
    no caller to authorise -- the run row already named the startup and its
    owner, and the service call that created it did check
    (`audit.service.request_audit`). Inventing an actor here is how a background
    job ends up running as an implicit superuser; the same reasoning as
    `workers.tasks._snapshot_for`.

    **Reconciled, never rewritten.** Every audit produces a complete action plan,
    so the naive implementation -- delete this startup's tasks and insert the new
    plan -- would throw away the founder's progress on every task each time they
    re-audit. Three cases, keyed by `generation.action_fingerprint`:

    * **The gap is new.** Insert it as `open`.
    * **The gap is already stored.** Refresh the things the new audit is
      authoritative about -- `requirement`, `dimension_score`, `is_priority`, and
      which run is asking -- and leave `status` alone. A task the founder has
      submitted evidence for stays submitted; one that was `obsolete` reopens,
      because the gap has come back.
    * **A stored task the new audit does not raise.** Retired to `obsolete`, but
      only if nobody has touched it (`UNTOUCHED_STATUSES`). Anything carrying
      evidence keeps its state and its history.

    The `action` text itself is refreshed too: the wording is regenerated every
    run and the founder should read what the current report says, not what a
    superseded one did. The fingerprint normalises whitespace and case, so a
    refresh here means the model genuinely re-punctuated the same instruction.

    **Runs in the caller's transaction and does not commit.** The worker stores
    the report and generates the tasks together, so a founder is never told
    "not yet" by a report whose action plan reached nothing they can act on.

    Returns every task now live for this startup from this plan, in plan order.
    """
    generated = plan_for_report(report)
    repository = ReadinessTaskRepository(session)

    fingerprints = [task.fingerprint for task in generated]
    existing = await repository.find_by_fingerprints(startup_id, fingerprints)

    live: list[ReadinessTask] = []
    for task in generated:
        stored = existing.get(task.fingerprint)
        if stored is None:
            live.append(
                await repository.add(
                    _new_task(
                        task,
                        startup_id=startup_id,
                        owner_id=owner_id,
                        audit_run_id=audit_run_id,
                    )
                )
            )
            continue
        _refresh(stored, task, audit_run_id=audit_run_id)
        live.append(stored)

    retired = await _retire_unraised(
        repository, startup_id=startup_id, raised=set(fingerprints)
    )

    await session.flush()

    logger.info(
        "readiness tasks generated",
        extra={
            "context": {
                "startup_id": str(startup_id),
                "audit_run_id": str(audit_run_id),
                "generated": len(generated),
                "required": required_count(generated),
                "created": len(generated) - len(existing),
                "retired": retired,
            }
        },
    )
    return tuple(live)


def _new_task(
    task: GeneratedTask,
    *,
    startup_id: uuid.UUID,
    owner_id: uuid.UUID,
    audit_run_id: uuid.UUID,
) -> ReadinessTask:
    return ReadinessTask(
        startup_id=startup_id,
        owner_id=owner_id,
        audit_run_id=audit_run_id,
        dimension=task.dimension,
        action=task.action,
        action_fingerprint=task.fingerprint,
        requirement=task.requirement,
        status=TaskStatus.OPEN,
        dimension_score=task.dimension_score,
        is_priority=task.is_priority,
    )


def _refresh(
    stored: ReadinessTask, task: GeneratedTask, *, audit_run_id: uuid.UUID
) -> None:
    """Apply what the new audit is authoritative about, and nothing more.

    `status` is absent from this list except for the one transition that is
    genuinely news: a task retired as `obsolete` and raised again means the gap
    reopened, and leaving it retired would hide a regression from the founder.
    Every other status is the evidence loop's to move (T3.5).
    """
    stored.audit_run_id = audit_run_id
    stored.action = task.action
    stored.requirement = task.requirement
    stored.dimension_score = task.dimension_score
    stored.is_priority = task.is_priority
    if stored.status is TaskStatus.OBSOLETE:
        stored.status = TaskStatus.OPEN


async def _retire_unraised(
    repository: ReadinessTaskRepository,
    *,
    startup_id: uuid.UUID,
    raised: set[str],
) -> int:
    """Retire the untouched tasks this audit no longer asks for.

    Scoped to `UNTOUCHED_STATUSES` in the query rather than filtered afterwards,
    so the rows carrying evidence are never even loaded as candidates.
    """
    retired = 0
    for stored in await repository.list_by_status(
        startup_id, tuple(UNTOUCHED_STATUSES)
    ):
        if stored.action_fingerprint in raised:
            continue
        stored.status = TaskStatus.OBSOLETE
        retired += 1
    return retired


async def list_tasks(
    session: AsyncSession,
    actor: CurrentUser,
    startup_id: uuid.UUID,
    *,
    status: TaskStatus | None = None,
    requirement: Requirement | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ReadinessTask], int]:
    """This startup's tasks, for its owner or an admin.

    Ownership is checked on the profile rather than on each row, matching
    `audit.service.list_audit_runs`: a list has no single object to authorise,
    and the profile is the tenant boundary every task hangs off.
    """
    profile = await intake.get_profile(session, actor, startup_id)
    return await ReadinessTaskRepository(session).list_for_startup(
        profile.id,
        status=status,
        requirement=requirement,
        limit=limit,
        offset=offset,
    )


async def get_task(
    session: AsyncSession,
    actor: CurrentUser,
    startup_id: uuid.UUID,
    task_id: uuid.UUID,
) -> ReadinessTask:
    """One task, for its owner or an admin.

    A straight IDOR surface -- `task_id` names a row belonging to exactly one
    founder -- so the same shape as `audit.service.get_audit_run`: the
    `startup_id` in the path is checked *against the row* rather than trusted,
    and a mismatch is folded into the same `404` as "no such task". Without that
    check a caller could pass their own startup's path with someone else's task
    id and learn from the status code that the id is real.
    """
    task = await ReadinessTaskRepository(session).get(task_id)
    if task is not None and task.startup_id != startup_id:
        task = None
    return owned_or_404(task, actor, message=_TASK_DENIED)


async def summarise_tasks(
    session: AsyncSession, actor: CurrentUser, startup_id: uuid.UUID
) -> ReadinessSummary:
    """Counts and gate state for the founder's home screen (T3.1, T3.6).

    **Scoped to the tasks the latest succeeded audit raised**, because that is
    what the discovery gate counts. `audit_run_id` is refreshed to the newest
    run on every regeneration, so it identifies the current plan exactly.

    Counting every task ever generated instead would be a progress bar that can
    never reach zero: a task graded `failed` keeps that status even after a
    later audit stops raising the gap -- `UNTOUCHED_STATUSES` retires only
    untouched rows, deliberately, so a founder's evidence is never erased -- and
    a gap absent from the current report is one no new evidence can address.

    **`obsolete` is excluded as well.** A retired task is not work the founder
    owes. It cannot co-occur with the latest run id today (`_refresh` reopens
    it), so this is defensive rather than load-bearing.

    Returns zeros and `has_audit=False` when no audit has succeeded. That is not
    an error -- there is genuinely nothing to report yet.
    """
    profile = await intake.get_profile(session, actor, startup_id)
    latest = await AuditRunRepository(session).latest_succeeded(profile.id)

    if latest is None:
        return _summarise((), has_audit=False, opted_in=profile.investor_visible)

    rows, _ = await ReadinessTaskRepository(session).list_for_startup(
        profile.id, audit_run_id=latest.id, limit=_ALL_TASKS, offset=0
    )
    return _summarise(rows, has_audit=True, opted_in=profile.investor_visible)


_ALL_TASKS = 1000
"""Ceiling on the rows a summary counts.

The largest real plan so far was 44 items, and the rubric raises at most a few
per dimension across eleven dimensions, so this is roughly twenty times the
worst case rather than a limit anything is expected to meet. It exists so a
corrupted plan cannot pull an unbounded result set into memory on a screen that
loads at every app launch. If a startup ever genuinely exceeds it the counts
would silently under-report, which is why the ceiling is this far clear of the
data rather than snug against it.
"""


def _summarise(
    rows: Sequence[ReadinessTask], *, has_audit: bool, opted_in: bool
) -> ReadinessSummary:
    """The same arithmetic the discovery gate does, expressed for one founder.

    `gate_cleared` and `discoverable` are deliberately separate. Eligibility and
    consent fail for different reasons and are fixed by different actions, so
    collapsing them into one flag would leave a founder unable to tell "you have
    work left" from "you have not opted in".

    **`discoverable`, not `investor_visible`.** `StartupProfile.investor_visible`
    already exists and means consent *alone*; a second field with that name
    meaning consent-and-eligibility would be two different answers to the same
    question in two responses the same client reads.
    """
    live = [row for row in rows if row.status is not TaskStatus.OBSOLETE]
    required = [row for row in live if row.requirement is Requirement.REQUIRED]
    passed = [row for row in required if row.status is TaskStatus.PASSED]
    outstanding = len(required) - len(passed)
    cleared = has_audit and outstanding == 0
    return ReadinessSummary(
        total=len(live),
        required_total=len(required),
        required_open=outstanding,
        required_passed=len(passed),
        recommended_total=len(live) - len(required),
        has_audit=has_audit,
        gate_cleared=cleared,
        discoverable=cleared and opted_in,
    )


# ---------------------------------------------------------------------------
# Evidence (T3.5)
# ---------------------------------------------------------------------------

_EVIDENCE_DENIED = "No such evidence."


async def get_task_by_id(
    session: AsyncSession, actor: CurrentUser, task_id: uuid.UUID
) -> ReadinessTask:
    """One task by id alone, for its owner or an admin.

    Separate from `get_task` because the evidence routes are nested under the
    *task*, not under the startup, so there is no `startup_id` in the path to
    check against. That is deliberate: an evidence URL carrying a startup id
    would invite a client to construct one, and the task id already names
    exactly one startup.
    """
    return owned_or_404(
        await ReadinessTaskRepository(session).get(task_id),
        actor,
        message=_TASK_DENIED,
    )


async def request_evidence_upload(
    session: AsyncSession,
    actor: CurrentUser,
    task_id: uuid.UUID,
    *,
    filename: str,
    content_type: str,
) -> tuple[Evidence, str]:
    """Reserve an evidence row and hand back a signed URL to `PUT` it to.

    Mirrors `intake.request_upload` exactly -- the row exists before the file,
    the storage key is server-generated and never negotiated with the client,
    and the URL is returned but never persisted, because a credential in a
    column is a credential in every backup.

    Two refusals specific to evidence, both `409` rather than `422` because
    nothing about the *request* is malformed -- the task is simply not in a
    state that accepts one:

    * **The task already passed.** Nothing is left to prove, and a further
      graded attempt is a billed call that can only take a passed task
      backwards.
    * **The attempt cap is reached.** `MAX_ASSESSMENT_ATTEMPTS` guards the
      investor-visibility gate against being ground down by repetition. Refused
      at the *start* of the flow rather than after the file arrives: letting a
      founder upload and then refusing to grade wastes their time and leaves
      bytes in the bucket to clean up.

    A task that is `obsolete` is still uploadable against. The founder may have
    been part-way through the work when a re-audit stopped raising the gap, and
    refusing them would discard that.
    """
    task = await get_task_by_id(session, actor, task_id)

    if task.status is TaskStatus.PASSED:
        raise ConflictError(
            "This task has already passed. There is nothing more to submit."
        )

    if task.assessment_attempts >= MAX_ASSESSMENT_ATTEMPTS:
        raise ConflictError(
            "You have used all assessment attempts for this task. Contact "
            "support to have it reopened."
        )

    if not is_allowed_content_type(content_type):
        raise InvalidRequestError(
            "That file type cannot be uploaded.",
            {"field": "content_type", "reason": "unsupported_content_type"},
        )

    evidence_id = uuid.uuid4()
    # Scoped by startup, keyed by evidence -- both server-generated UUIDs, so
    # the founder's filename never reaches the key.
    key = object_key(task.startup_id, evidence_id)

    evidence = await EvidenceRepository(session).add(
        Evidence(
            id=evidence_id,
            task_id=task.id,
            owner_id=task.owner_id,
            startup_id=task.startup_id,
            filename=safe_filename(filename),
            storage_key=key,
            status=EvidenceStatus.PENDING,
        )
    )
    url = signed_upload_url(key, content_type=content_type, bucket="evidence")
    return evidence, url


async def complete_evidence_upload(
    session: AsyncSession, actor: CurrentUser, evidence_id: uuid.UUID
) -> Evidence:
    """Confirm the upload arrived, then queue the task for grading.

    Judged on what actually landed in R2, never on what the client declared --
    the same rule as `intake.complete_upload`. A file that fails validation is
    deleted from the bucket and the row kept, so the founder gets a reason
    instead of watching an upload disappear.

    On success the task moves to `submitted` **before** the grader runs, so a
    founder polling sees their submission acknowledged rather than sitting on
    `open` for a minute wondering whether the upload worked.

    Idempotent: calling it again on an already-confirmed row returns it
    unchanged and does **not** dispatch a second grading. A double-tapped button
    that billed two `AUDIT`-tier calls is the same class of bug the audit run's
    lease exists to prevent.

    **The cap is re-checked here, not only at reservation.** Checking it once, at
    `request_evidence_upload`, left it trivially bypassable: reservations are
    cheap and unmetered, so a founder could reserve ten tickets while the counter
    read zero and then complete them one at a time afterwards, each completion
    dispatching a grading that pushed the counter past its ceiling unchecked.
    That defeats the guard on the investor-visibility gate entirely. The state
    that matters is the state **at the moment work is dispatched**, so that is
    where it is tested.

    Refused before the object is read back, so a founder past the cap costs no
    storage call. The bytes they already `PUT` stay in the bucket on a `pending`
    row -- the same untidiness a document upload that never completes leaves, and
    the same absent cleanup path (v1).
    """
    evidence = owned_or_404(
        await EvidenceRepository(session).get(evidence_id),
        actor,
        message=_EVIDENCE_DENIED,
    )
    if evidence.status is not EvidenceStatus.PENDING:
        return evidence

    task = await ReadinessTaskRepository(session).get(evidence.task_id)
    if task is not None:
        if task.status is TaskStatus.PASSED:
            raise ConflictError(
                "This task has already passed. There is nothing more to submit."
            )
        if task.assessment_attempts >= MAX_ASSESSMENT_ATTEMPTS:
            raise ConflictError(
                "You have used all assessment attempts for this task. Contact "
                "support to have it reopened."
            )

    stored = head_object(evidence.storage_key, bucket="evidence")
    if stored is None:
        raise InvalidRequestError(
            "That upload has not arrived yet.",
            {"field": "evidence_id", "reason": "object_missing"},
        )

    rejection = _rejection_reason(stored)
    if rejection is not None:
        # Deleted before the row is updated: a file that failed validation must
        # not sit in the bucket waiting for someone to find a way to read it.
        delete_object(evidence.storage_key, bucket="evidence")
        evidence.status = EvidenceStatus.REJECTED
        evidence.size_bytes = stored.size_bytes
        evidence.content_type = stored.content_type
        await session.flush()
        logger.info(
            "evidence upload rejected", extra={"context": {"reason": rejection}}
        )
        raise InvalidRequestError(
            "That upload was rejected.",
            {"field": "evidence_id", "reason": rejection},
        )

    evidence.size_bytes = stored.size_bytes
    evidence.content_type = stored.content_type
    evidence.status = EvidenceStatus.READY

    if task is not None:
        task.status = TaskStatus.SUBMITTED
    await session.flush()

    enqueue_assessment(evidence.task_id)
    return evidence


def _rejection_reason(stored: StoredObject) -> str | None:
    """Why this object is not acceptable, or `None` if it is.

    Deliberately identical to `intake.service._rejection_reason` in both rules
    and reason strings: a founder should not discover that a file acceptable as
    a pitch deck is refused as evidence. The limits come from the same module so
    the two cannot drift on numbers; only this ordering is repeated, and it is
    repeated rather than shared because `intake` importing `readiness` would
    invert a dependency that currently runs one way.
    """
    if stored.size_bytes > MAX_UPLOAD_BYTES:
        return "file_too_large"
    if stored.size_bytes == 0:
        return "empty_file"
    if not is_allowed_content_type(stored.content_type):
        return "unsupported_content_type"
    return None


async def list_evidence(
    session: AsyncSession,
    actor: CurrentUser,
    task_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Evidence], int]:
    """This task's submissions, newest first. Ownership is checked on the task."""
    task = await get_task_by_id(session, actor, task_id)
    return await EvidenceRepository(session).list_for_task(
        task.id, limit=limit, offset=offset
    )


async def get_evidence(
    session: AsyncSession, actor: CurrentUser, evidence_id: uuid.UUID
) -> Evidence:
    """One submission, for its owner or an admin."""
    return owned_or_404(
        await EvidenceRepository(session).get(evidence_id),
        actor,
        message=_EVIDENCE_DENIED,
    )


async def evidence_download_url(
    session: AsyncSession, actor: CurrentUser, evidence_id: uuid.UUID
) -> tuple[Evidence, str]:
    """A short-lived signed URL for a submission the caller is entitled to.

    A `rejected` row has no bytes -- they were deleted at validation -- so it is
    `404` rather than a URL that resolves to nothing.
    """
    evidence = await get_evidence(session, actor, evidence_id)
    if evidence.status is EvidenceStatus.REJECTED:
        raise NotFoundError("That upload was rejected and is no longer stored.")
    if evidence.status is EvidenceStatus.PENDING:
        raise NotFoundError("That upload has not arrived yet.")

    url = signed_download_url(
        evidence.storage_key, filename=evidence.filename, bucket="evidence"
    )
    return evidence, url


async def reopen_task(
    session: AsyncSession, actor: CurrentUser, task_id: uuid.UUID
) -> ReadinessTask:
    """Clear a task's attempt cap so the founder can submit again. **Admin only.**

    The only way past `MAX_ASSESSMENT_ATTEMPTS`, which is why it is an admin
    action and why it is written to the immutable audit log: this is the single
    lever that undoes the guard on the investor-visibility gate, so who pulled
    it and for which task has to be reconstructable afterwards (`CLAUDE.md`
    section 4).

    Resets the counter and returns the task to `open`. A `passed` task is
    reopenable too, deliberately -- that is the dispute path for a grading
    somebody believes was wrong, and refusing it here would make a database edit
    the only way to correct a false pass.
    """
    assert_admin(actor, message="Only a SACI admin can reopen a task.")

    task = await ReadinessTaskRepository(session).get(task_id)
    if task is None:
        raise NotFoundError(_TASK_DENIED)

    previous_attempts = task.assessment_attempts
    task.assessment_attempts = 0
    task.status = TaskStatus.OPEN
    await session.flush()

    await identity.record_action(
        session,
        AuditAction.TASK_REOPENED,
        actor_id=actor.id,
        target_type="readiness_task",
        target_id=task.id,
        details={"previous_attempts": previous_attempts},
    )
    return task


_TASK_STATUS_FOR: Final[dict[AssessmentOutcome, TaskStatus]] = {
    AssessmentOutcome.PASS: TaskStatus.PASSED,
    AssessmentOutcome.FAIL: TaskStatus.FAILED,
    AssessmentOutcome.NEEDS_MORE: TaskStatus.NEEDS_MORE,
}
"""The grader's vocabulary mapped to the task's.

Two enums rather than one shared set of values, because they answer different
questions: `AssessmentOutcome` is what the model said about a submission,
`TaskStatus` is where the task now sits. Collapsing them would make the model's
output *be* the task state, which is the "uploads must not act as instructions"
line `CLAUDE.md` section 5 draws. This mapping is the seam that keeps a model
from writing a status directly.
"""


async def record_assessment(
    session: AsyncSession,
    *,
    task_id: uuid.UUID,
    graded: Sequence[uuid.UUID],
    outcome: AssessmentOutcome,
    reasons: Sequence[str],
    prompt_ref: str,
) -> None:
    """Write one grading to every submission it covered, and move the task.

    **No `CurrentUser`.** Called by the worker, which has no caller to
    authorise -- the same reasoning as `generate_for_report`.

    The attempt counter increments **here, on the grading**, not on the upload.
    A founder who attaches three files to one task has made one attempt, because
    the grader read them together as a single submission; counting uploads would
    let one careful submission exhaust the cap.
    """
    task = await ReadinessTaskRepository(session).get(task_id)
    if task is None:  # pragma: no cover - deleted mid-flight
        return

    now = datetime.now(UTC)
    repository = EvidenceRepository(session)
    for evidence_id in graded:
        evidence = await repository.get(evidence_id)
        if evidence is None:  # pragma: no cover - deleted mid-flight
            continue
        evidence.outcome = outcome
        evidence.reasons = list(reasons)
        evidence.assessment_prompt_ref = prompt_ref
        evidence.assessed_at = now

    task.status = _TASK_STATUS_FOR[outcome]
    task.assessment_attempts += 1
    await session.flush()

    logger.info(
        "evidence assessed",
        extra={
            "context": {
                "task_id": str(task_id),
                "outcome": outcome.value,
                "submissions": len(graded),
                "attempts": task.assessment_attempts,
            }
        },
    )


async def record_assessment_failure(
    session: AsyncSession, *, task_id: uuid.UUID, graded: Sequence[uuid.UUID]
) -> None:
    """Grading could not be completed. Return the task, charge no attempt.

    A provider outage is not a founder's mistake, so it must not consume one of
    three attempts, and the task must not read `submitted` forever with nothing
    coming. The task returns to `open` so the founder can resubmit, and each
    submission carries `error_code` so the client can say what happened instead
    of showing a silent nothing.
    """
    task = await ReadinessTaskRepository(session).get(task_id)
    if task is not None:
        task.status = TaskStatus.OPEN

    repository = EvidenceRepository(session)
    for evidence_id in graded:
        evidence = await repository.get(evidence_id)
        if evidence is not None:
            evidence.error_code = "assessment_failed"
    await session.flush()


async def passed_evidence_keys(
    session: AsyncSession, startup_id: uuid.UUID
) -> list[str]:
    """Storage keys of the evidence a re-audit should read (T3.6).

    **This is what makes a re-audit mean something.** `input_fingerprint` hashes
    the document keys, so evidence passing changes the hash and
    `audit.request_audit` mints a genuinely new run instead of handing back the
    verdict from before the work was done -- a regression that would look
    exactly like the idempotency cache working correctly.

    Keys rather than bytes, and separate from `load_passed_evidence`, for the
    reason `intake.auditable_storage_keys` gives: the fingerprint is computed on
    the request thread, long before anything is fetched, and it must not fetch.

    No ownership check -- the caller has already authorised the startup, and
    this returns opaque keys rather than content.
    """
    rows = await EvidenceRepository(session).list_passed_for_startup(startup_id)
    return [row.storage_key for row in rows]


async def load_passed_evidence(
    session: AsyncSession, startup_id: uuid.UUID
) -> tuple[list[DocumentPayload], list[str]]:
    """Fetch the bytes of every passed submission. Payloads and failures.

    **No ownership check, deliberately**, for the reason
    `intake.load_auditable_documents` gives: there is no caller to authorise.
    The AuditRun already named this startup and was written by a service call
    that did check.

    A submission whose object has gone missing is **skipped and named** rather
    than failing the audit, the same rule documents follow. Losing one piece of
    proof should cost that proof, not the whole re-audit a founder has been
    working towards.

    Returned as `DocumentPayload` -- the same plain-data shape documents use --
    so the worker's composition root maps both into `SourceDocument` without
    `audit` learning what an `Evidence` row is.
    """
    rows = await EvidenceRepository(session).list_passed_for_startup(startup_id)

    payloads: list[DocumentPayload] = []
    unreadable: list[str] = []
    for row in rows:
        try:
            content = get_object(row.storage_key, bucket="evidence")
        except Exception:
            logger.exception(
                "a passed submission could not be fetched; auditing without it",
                extra={"context": {"evidence_id": str(row.id)}},
            )
            unreadable.append(str(row.id))
            continue
        if content is None:
            unreadable.append(str(row.id))
            continue
        payloads.append(
            DocumentPayload(
                document_id=str(row.id),
                filename=row.filename,
                content_type=row.content_type or "application/octet-stream",
                content=content,
            )
        )
    return payloads, unreadable
