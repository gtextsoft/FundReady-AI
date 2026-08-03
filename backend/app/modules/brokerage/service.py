"""Brokerage business logic (T4.5, T4.6).

Layer: **service** (ARCHITECTURE.md section 3) -- business logic and
orchestration. Performs authorization and ownership checks (AUTH.md sections
5-6), calls this module's `repository`, `app.ai`, and other modules' public
service functions only (never their internals). Enqueues background jobs.
Selects the tier serializer for every response carrying report data
(DECISIONS.md D8).

**This module is where SACI actually stands between the two sides.** Everywhere
else, report tiers are a serializer declining to emit a field. Here is the one
sanctioned exception `CLAUDE.md` section 4 allows -- a full report reaching
somebody who does not own it -- and it is gated three ways: only an admin may
call it, only against an approved interest, and every call writes an immutable
audit-log row naming who opened what for whom.

**Approval and reveal are deliberately two actions.** Approving says SACI will
broker the introduction; revealing hands over the founder's full audit. Merging
them would make the consequential step a side effect of the routine one, and the
routine one is the step somebody clicks through a queue of.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.security import CurrentUser, Role
from app.modules.audit.models import AuditRun
from app.modules.audit.reports import AdminReport, admin_report
from app.modules.audit.repository import AuditRunRepository
from app.modules.audit.runs import AuditStatus
from app.modules.brokerage.models import Interest, InterestStatus
from app.modules.brokerage.repository import InterestRepository, RevealRepository
from app.modules.brokerage.schemas import InterestResponse, RevealResponse
from app.modules.identity import service as identity
from app.modules.identity.models import AuditAction
from app.modules.investor import service as investor

__all__ = [
    "decide_interest",
    "express_interest",
    "list_interests",
    "read_revealed_report",
    "reveal_report",
]

_NOT_FOUND = "No such interest."
"""One wording for "no such row" and "not yours" -- see `core.ownership`."""


def _require_admin(actor: CurrentUser) -> None:
    if actor.role is not Role.ADMIN:
        raise ForbiddenError


async def _owned_interest(
    session: AsyncSession, actor: CurrentUser, interest_id: uuid.UUID
) -> Interest:
    """The interest, if this caller may see it. Admins may see any."""
    interest = await InterestRepository(session).get(interest_id)
    if interest is None:
        raise NotFoundError(_NOT_FOUND)
    if actor.role is not Role.ADMIN and interest.investor_id != actor.id:
        raise NotFoundError(_NOT_FOUND)
    return interest


async def express_interest(
    session: AsyncSession,
    actor: CurrentUser,
    startup_id: uuid.UUID,
    *,
    note: str | None = None,
) -> InterestResponse:
    """An investor asks SACI to introduce them to one startup.

    **Routed through `investor.visible_startup` rather than reading the profile
    directly.** That reuses the discovery filter, so an investor cannot express
    interest in a startup that has not published itself by pasting an id they
    were never shown -- the same guard protects the browse and the write.

    Repeating an expression returns the original row instead of erroring. The
    unique constraint would refuse the insert anyway; answering with what
    already exists is the more useful response to a client that retried.
    """
    investor.require_investor(actor)
    await investor.visible_startup(session, actor, startup_id)

    repository = InterestRepository(session)
    existing = await repository.for_pair(actor.id, startup_id)
    if existing is not None:
        return InterestResponse.of(existing)

    interest = await repository.create(
        investor_id=actor.id, startup_id=startup_id, note=note
    )
    await identity.record_action(
        session,
        AuditAction.INTEREST_EXPRESSED,
        actor_id=actor.id,
        target_type="startup_profile",
        target_id=startup_id,
        details={"interest_id": str(interest.id)},
    )
    return InterestResponse.of(interest)


async def list_interests(
    session: AsyncSession,
    actor: CurrentUser,
    *,
    status: InterestStatus | None = None,
) -> list[InterestResponse]:
    """An investor's own interests, or every interest for a SACI admin."""
    repository = InterestRepository(session)
    reveals = RevealRepository(session)

    if actor.role is Role.ADMIN:
        rows = await repository.list_all(status=status)
    else:
        investor.require_investor(actor)
        rows = await repository.list_for_investor(actor.id)
        if status is not None:
            rows = [row for row in rows if row.status is status]

    out = []
    for row in rows:
        revealed = await reveals.list_for_interest(row.id)
        out.append(
            InterestResponse.of(row, [reveal.audit_run_id for reveal in revealed])
        )
    return out


async def decide_interest(
    session: AsyncSession,
    actor: CurrentUser,
    interest_id: uuid.UUID,
    *,
    approve: bool,
) -> InterestResponse:
    """SACI approves or declines. **Admins only, and one decision per interest.**

    A decided interest cannot be re-decided. Not stubbornness: the audit log
    records the decision that was taken, and flipping it later would leave two
    contradictory rows with no way to tell which governed. Reversing a decision
    is a support conversation, deliberately.
    """
    _require_admin(actor)
    interest = await _owned_interest(session, actor, interest_id)

    if interest.status is not InterestStatus.PENDING:
        raise ConflictError(f"This interest is already {interest.status.value}.")

    interest.status = InterestStatus.APPROVED if approve else InterestStatus.DECLINED
    interest.decided_at = datetime.now(UTC)
    interest.decided_by_id = actor.id
    await session.flush()

    await identity.record_action(
        session,
        AuditAction.INTEREST_APPROVED if approve else AuditAction.INTEREST_DECLINED,
        actor_id=actor.id,
        target_type="interest",
        target_id=interest.id,
        details={"startup_id": str(interest.startup_id)},
    )
    return InterestResponse.of(interest)


async def _latest_succeeded_run(
    session: AsyncSession, startup_id: uuid.UUID
) -> AuditRun:
    runs = await AuditRunRepository(session).list_for_startup(startup_id, limit=20)
    for run in runs:
        if run.status is AuditStatus.SUCCEEDED and run.report is not None:
            return run
    raise NotFoundError("This startup has no completed audit to reveal.")


async def reveal_report(
    session: AsyncSession,
    actor: CurrentUser,
    interest_id: uuid.UUID,
) -> RevealResponse:
    """Open one startup's full report to one investor. **The gate.**

    Three conditions, all required:

    * the caller is a SACI admin;
    * the interest has been **approved** -- revealing against a pending or
      declined interest would make approval decorative;
    * the startup has a succeeded audit to reveal.

    Revealing twice is idempotent rather than a second disclosure: the unique
    constraint on `(interest_id, audit_run_id)` says so in the database, and
    returning the existing row means a retried request does not write a second
    audit-log entry implying it happened twice.

    The reveal names a **run**, not a startup. A founder who re-audits after
    fixing their figures has produced a different report, and this investor's
    access is to what they were actually shown.
    """
    _require_admin(actor)
    interest = await _owned_interest(session, actor, interest_id)

    if interest.status is not InterestStatus.APPROVED:
        raise ConflictError(
            "Approve this interest before revealing a report to the investor."
        )

    run = await _latest_succeeded_run(session, interest.startup_id)
    reveals = RevealRepository(session)

    existing = await reveals.get_for(interest.id, run.id)
    if existing is not None:
        return RevealResponse(
            interest_id=interest.id,
            audit_run_id=run.id,
            revealed_at=existing.revealed_at,
        )

    reveal = await reveals.create(
        interest_id=interest.id, audit_run_id=run.id, revealed_by_id=actor.id
    )
    await identity.record_action(
        session,
        AuditAction.REPORT_REVEALED,
        actor_id=actor.id,
        target_type="audit_run",
        target_id=run.id,
        details={
            "interest_id": str(interest.id),
            "investor_id": str(interest.investor_id),
            "startup_id": str(interest.startup_id),
        },
    )
    return RevealResponse(
        interest_id=interest.id,
        audit_run_id=run.id,
        revealed_at=reveal.revealed_at,
    )


async def read_revealed_report(
    session: AsyncSession,
    actor: CurrentUser,
    interest_id: uuid.UUID,
    run_id: uuid.UUID,
) -> AdminReport:
    """The full report an investor has been shown.

    **The only path by which an investor ever reads full report content**, and
    it is checked against a `ReportReveal` row rather than against the
    interest's status: approval is not disclosure, and an investor whose
    interest was approved but never revealed gets `404` here.

    Served with `admin_report` because a reveal is exactly the decision that the
    full document may be seen -- withholding a field at this point would be
    theatre, since SACI has already opened it deliberately at a meeting.
    """
    interest = await _owned_interest(session, actor, interest_id)

    reveal = await RevealRepository(session).get_for(interest.id, run_id)
    if reveal is None:
        raise NotFoundError("No report has been revealed to you for this startup.")

    run = await AuditRunRepository(session).get(run_id)
    if run is None or run.report is None:
        raise NotFoundError("That report is no longer available.")

    return admin_report(run.report)
