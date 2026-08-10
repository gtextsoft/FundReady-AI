"""Evidence isolation and the attempt cap (T3.5).

Two separate guarantees, both tested here because both are walls rather than
features.

**Tenant isolation.** `/v1/evidence/{id}/...` and `/v1/tasks/{id}/evidence` take
ids straight from the client and name rows belonging to exactly one founder.
The download route is the sharpest: it hands back a signed URL to a private
file, so a missed ownership check is not an information leak about ids, it is
the file itself.

**The attempt cap.** `MAX_ASSESSMENT_ATTEMPTS` is the only thing stopping a
founder grinding the grader until something passes and walking into investor
visibility. It has to be enforced server-side, it has to survive a client that
simply ignores `attempts_remaining`, and the only way past it has to be an
admin action that is written to the immutable audit log.
"""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.security import AccountStatus, CurrentUser, Role
from app.modules.audit import service as audit
from app.modules.identity import service as identity
from app.modules.identity.models import AuditAction, AuditLog, User
from app.modules.intake import service as intake
from app.modules.intake.fields import Stage
from app.modules.readiness import service as readiness
from app.modules.readiness.evidence import (
    MAX_ASSESSMENT_ATTEMPTS,
    AssessmentOutcome,
    EvidenceStatus,
)
from app.modules.readiness.generation import Requirement, TaskStatus
from app.modules.readiness.models import Evidence, ReadinessTask
from tests.conftest import requires_database

pytestmark = [pytest.mark.security, pytest.mark.integration, requires_database]

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-signing-key-at-least-32-characters")
    monkeypatch.setenv("ARGON2_MEMORY_COST_KIB", "8192")
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def no_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither Redis nor R2 is a party to an authorization test."""
    monkeypatch.setattr(audit, "enqueue_audit", lambda _run_id: None)
    monkeypatch.setattr(readiness, "enqueue_assessment", lambda _task_id: None)
    monkeypatch.setattr(
        readiness, "signed_upload_url", lambda *_a, **_k: "https://upload.test/x"
    )
    monkeypatch.setattr(
        readiness, "signed_download_url", lambda *_a, **_k: "https://download.test/x"
    )


def _actor(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        role=user.role,
        status=AccountStatus.ACTIVE,
        email_verified=True,
        mfa_enabled=user.mfa_enabled,
    )


async def _founder(
    session: AsyncSession, role: Role = Role.FOUNDER
) -> tuple[User, CurrentUser]:
    user = await identity.register_user(
        session,
        email=f"user-{uuid.uuid4().hex}@example.test",
        password=PASSWORD,
        role=Role.FOUNDER,
        first_name="Ada",
        last_name="Tester",
    )
    assert user is not None
    user.role = role
    user.status = AccountStatus.ACTIVE
    if role is Role.ADMIN:
        user.mfa_enabled = True
    await session.flush()
    return user, _actor(user)


_AUDITABLE = {
    "description": {"value": "Last-mile delivery for Lagos pharmacies."},
    "business_model": {"value": "Per-delivery fee plus a subscription."},
    "team_size": {"value": 10},
    "monthly_revenue_minor": {"value": 5_000_000},
    "monthly_costs_minor": {"value": 4_000_000},
    "cash_on_hand_minor": {"value": 20_000_000},
}


async def _task_for(
    session: AsyncSession, user: User, actor: CurrentUser
) -> ReadinessTask:
    """A founder with a profile and one open readiness task."""
    profile = await intake.create_profile(
        session,
        actor,
        {
            "name": "Kanmi Logistics",
            "sector": "last-mile delivery",
            "stage": Stage.SEED,
            "country": "NG",
            "currency": "NGN",
            "fields": dict(_AUDITABLE),
        },
    )
    task = ReadinessTask(
        startup_id=profile.id,
        owner_id=user.id,
        dimension="traction",
        action="Publish a pricing page.",
        action_fingerprint=uuid.uuid4().hex * 2,
        requirement=Requirement.REQUIRED,
        status=TaskStatus.OPEN,
    )
    session.add(task)
    await session.flush()
    return task


async def _upload(
    session: AsyncSession, actor: CurrentUser, task: ReadinessTask
) -> Evidence:
    evidence, _ = await readiness.request_evidence_upload(
        session, actor, task.id, filename="proof.png", content_type="image/png"
    )
    return evidence


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


class TestIsolation:
    async def test_a_founder_uploads_against_their_own_task(
        self, db_session: AsyncSession
    ) -> None:
        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)

        evidence, url = await readiness.request_evidence_upload(
            db_session, actor, task.id, filename="proof.png", content_type="image/png"
        )

        assert evidence.status is EvidenceStatus.PENDING
        assert evidence.owner_id == user.id
        assert url

    async def test_uploading_against_another_founders_task_is_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """404, not 403. A 403 would confirm the task id is real."""
        owner_user, owner = await _founder(db_session)
        task = await _task_for(db_session, owner_user, owner)
        _, intruder = await _founder(db_session)

        with pytest.raises(NotFoundError):
            await readiness.request_evidence_upload(
                db_session,
                intruder,
                task.id,
                filename="proof.png",
                content_type="image/png",
            )

    async def test_another_founders_evidence_cannot_be_read(
        self, db_session: AsyncSession
    ) -> None:
        owner_user, owner = await _founder(db_session)
        task = await _task_for(db_session, owner_user, owner)
        evidence = await _upload(db_session, owner, task)
        _, intruder = await _founder(db_session)

        with pytest.raises(NotFoundError):
            await readiness.get_evidence(db_session, intruder, evidence.id)

    async def test_another_founders_evidence_cannot_be_downloaded(
        self, db_session: AsyncSession
    ) -> None:
        """The sharpest one: this route hands back a URL to the private file."""
        owner_user, owner = await _founder(db_session)
        task = await _task_for(db_session, owner_user, owner)
        evidence = await _upload(db_session, owner, task)
        evidence.status = EvidenceStatus.READY
        await db_session.flush()
        _, intruder = await _founder(db_session)

        with pytest.raises(NotFoundError):
            await readiness.evidence_download_url(db_session, intruder, evidence.id)

    async def test_another_founders_evidence_list_is_not_found(
        self, db_session: AsyncSession
    ) -> None:
        owner_user, owner = await _founder(db_session)
        task = await _task_for(db_session, owner_user, owner)
        _, intruder = await _founder(db_session)

        with pytest.raises(NotFoundError):
            await readiness.list_evidence(db_session, intruder, task.id)

    async def test_an_admin_may_read_evidence_across_tenants(
        self, db_session: AsyncSession
    ) -> None:
        """SACI reviews a disputed grading, so it needs the file (PRD section 3)."""
        owner_user, owner = await _founder(db_session)
        task = await _task_for(db_session, owner_user, owner)
        evidence = await _upload(db_session, owner, task)
        evidence.status = EvidenceStatus.READY
        await db_session.flush()
        _, admin = await _founder(db_session, role=Role.ADMIN)

        found = await readiness.get_evidence(db_session, admin, evidence.id)
        _, url = await readiness.evidence_download_url(db_session, admin, evidence.id)

        assert found.id == evidence.id
        assert url

    async def test_a_pending_upload_has_nothing_to_download(
        self, db_session: AsyncSession
    ) -> None:
        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)
        evidence = await _upload(db_session, actor, task)

        with pytest.raises(NotFoundError):
            await readiness.evidence_download_url(db_session, actor, evidence.id)

    async def test_a_rejected_upload_has_nothing_to_download(
        self, db_session: AsyncSession
    ) -> None:
        """Its bytes were deleted at validation, so a URL would resolve to nothing."""
        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)
        evidence = await _upload(db_session, actor, task)
        evidence.status = EvidenceStatus.REJECTED
        await db_session.flush()

        with pytest.raises(NotFoundError):
            await readiness.evidence_download_url(db_session, actor, evidence.id)


# ---------------------------------------------------------------------------
# The attempt cap
# ---------------------------------------------------------------------------


class TestAttemptCap:
    async def test_the_cap_refuses_a_further_upload(
        self, db_session: AsyncSession
    ) -> None:
        """Enforced server-side, so a client ignoring `attempts_remaining` fails.

        Without this, a founder can keep resubmitting until the grader passes
        something -- and the investor-visibility gate stops meaning anything.
        """
        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)
        task.assessment_attempts = MAX_ASSESSMENT_ATTEMPTS
        await db_session.flush()

        with pytest.raises(ConflictError):
            await readiness.request_evidence_upload(
                db_session,
                actor,
                task.id,
                filename="attempt-four.png",
                content_type="image/png",
            )

    async def test_the_last_attempt_is_still_allowed(
        self, db_session: AsyncSession
    ) -> None:
        """Off-by-one guard: the cap is a ceiling, not a fence one short of it."""
        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)
        task.assessment_attempts = MAX_ASSESSMENT_ATTEMPTS - 1
        await db_session.flush()

        evidence = await _upload(db_session, actor, task)

        assert evidence.status is EvidenceStatus.PENDING

    async def test_a_passed_task_accepts_no_further_evidence(
        self, db_session: AsyncSession
    ) -> None:
        """Nothing left to prove, and a further grading can only move it backwards."""
        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)
        task.status = TaskStatus.PASSED
        await db_session.flush()

        with pytest.raises(ConflictError):
            await readiness.request_evidence_upload(
                db_session,
                actor,
                task.id,
                filename="more.png",
                content_type="image/png",
            )

    async def test_grading_charges_exactly_one_attempt_per_submission_set(
        self, db_session: AsyncSession
    ) -> None:
        """Three files attached to one task is one attempt, not three.

        Counting uploads instead of gradings would let a single careful
        submission exhaust a founder's whole budget.
        """
        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)
        first = await _upload(db_session, actor, task)
        second = await _upload(db_session, actor, task)

        await readiness.record_assessment(
            db_session,
            task_id=task.id,
            graded=[first.id, second.id],
            outcome=AssessmentOutcome.NEEDS_MORE,
            reasons=["The screenshot carries no date."],
            prompt_ref="evidence_assessment@1",
        )

        assert task.assessment_attempts == 1
        assert task.status is TaskStatus.NEEDS_MORE
        assert first.reasons == ["The screenshot carries no date."]
        assert second.outcome is AssessmentOutcome.NEEDS_MORE

    async def test_needs_more_consumes_an_attempt(
        self, db_session: AsyncSession
    ) -> None:
        """It was a real call and a real shot at the grader.

        Exempting it would make `needs_more` an unlimited retry, which is the
        cap with extra steps.
        """
        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)
        evidence = await _upload(db_session, actor, task)

        await readiness.record_assessment(
            db_session,
            task_id=task.id,
            graded=[evidence.id],
            outcome=AssessmentOutcome.NEEDS_MORE,
            reasons=["Undated."],
            prompt_ref="evidence_assessment@1",
        )

        assert task.assessment_attempts == 1

    async def test_a_failed_grading_charges_no_attempt(
        self, db_session: AsyncSession
    ) -> None:
        """A provider outage is not the founder's mistake.

        The task returns to `open` so they can resubmit, and the counter is
        untouched -- otherwise a worker restart silently spends a founder's
        tries.
        """
        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)
        evidence = await _upload(db_session, actor, task)
        task.status = TaskStatus.SUBMITTED
        await db_session.flush()

        await readiness.record_assessment_failure(
            db_session, task_id=task.id, graded=[evidence.id]
        )

        assert task.assessment_attempts == 0
        assert task.status is TaskStatus.OPEN
        assert evidence.error_code == "assessment_failed"

    async def test_tickets_reserved_before_the_cap_cannot_be_cashed_after_it(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The bypass a reservation-time-only check leaves wide open.

        Reservations are cheap and unmetered, so a founder can take ten tickets
        while the counter reads zero and complete them one at a time afterwards.
        If `complete` does not re-check, each completion dispatches a grading and
        walks the counter past its ceiling -- and the guard on the
        investor-visibility gate stops meaning anything.

        The state that matters is the state at the moment work is dispatched,
        which is what this asserts.
        """
        from app.core.storage import StoredObject

        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)

        # Reserved while the founder is still under the cap.
        reserved = [await _upload(db_session, actor, task) for _ in range(3)]

        # ... and then the cap is reached by grading something else.
        task.assessment_attempts = MAX_ASSESSMENT_ATTEMPTS
        await db_session.flush()

        monkeypatch.setattr(
            readiness,
            "head_object",
            lambda *_a, **_k: StoredObject(size_bytes=1024, content_type="image/png"),
        )

        for ticket in reserved:
            with pytest.raises(ConflictError):
                await readiness.complete_evidence_upload(db_session, actor, ticket.id)

        assert task.assessment_attempts == MAX_ASSESSMENT_ATTEMPTS

    async def test_a_reserved_ticket_still_completes_while_under_the_cap(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The guard must not break the ordinary path it sits on."""
        from app.core.storage import StoredObject

        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)
        ticket = await _upload(db_session, actor, task)

        monkeypatch.setattr(
            readiness,
            "head_object",
            lambda *_a, **_k: StoredObject(size_bytes=1024, content_type="image/png"),
        )

        completed = await readiness.complete_evidence_upload(
            db_session, actor, ticket.id
        )

        assert completed.status is EvidenceStatus.READY
        assert task.status is TaskStatus.SUBMITTED

    async def test_a_ticket_cannot_be_cashed_against_a_passed_task(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same shape: reserve, then the task passes, then complete."""
        from app.core.storage import StoredObject

        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)
        ticket = await _upload(db_session, actor, task)

        task.status = TaskStatus.PASSED
        await db_session.flush()

        monkeypatch.setattr(
            readiness,
            "head_object",
            lambda *_a, **_k: StoredObject(size_bytes=1024, content_type="image/png"),
        )

        with pytest.raises(ConflictError):
            await readiness.complete_evidence_upload(db_session, actor, ticket.id)


# ---------------------------------------------------------------------------
# Reopening is the only way past the cap, and it is logged
# ---------------------------------------------------------------------------


class TestReopen:
    async def test_a_founder_cannot_reopen_their_own_task(
        self, db_session: AsyncSession
    ) -> None:
        """A counter the counted party can reset is not a cap."""
        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)
        task.assessment_attempts = MAX_ASSESSMENT_ATTEMPTS
        await db_session.flush()

        with pytest.raises(ForbiddenError):
            await readiness.reopen_task(db_session, actor, task.id)

        assert task.assessment_attempts == MAX_ASSESSMENT_ATTEMPTS

    async def test_an_investor_cannot_reopen_a_task(
        self, db_session: AsyncSession
    ) -> None:
        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)
        _, investor = await _founder(db_session, role=Role.INVESTOR)

        with pytest.raises(ForbiddenError):
            await readiness.reopen_task(db_session, investor, task.id)

    async def test_an_admin_reopen_clears_the_cap_and_is_logged(
        self, db_session: AsyncSession
    ) -> None:
        """The single lever that undoes the gate's guard, so who pulled it matters."""
        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)
        task.assessment_attempts = MAX_ASSESSMENT_ATTEMPTS
        task.status = TaskStatus.FAILED
        await db_session.flush()
        admin_user, admin = await _founder(db_session, role=Role.ADMIN)

        reopened = await readiness.reopen_task(db_session, admin, task.id)

        assert reopened.assessment_attempts == 0
        assert reopened.status is TaskStatus.OPEN

        logged = await db_session.scalars(
            select(AuditLog).where(
                AuditLog.action == AuditAction.TASK_REOPENED,
                AuditLog.target_id == str(task.id),
            )
        )
        entry = list(logged)
        assert len(entry) == 1
        assert entry[0].actor_id == admin_user.id
        assert entry[0].details["previous_attempts"] == MAX_ASSESSMENT_ATTEMPTS

    async def test_a_reopened_task_accepts_evidence_again(
        self, db_session: AsyncSession
    ) -> None:
        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)
        task.assessment_attempts = MAX_ASSESSMENT_ATTEMPTS
        await db_session.flush()
        _, admin = await _founder(db_session, role=Role.ADMIN)

        await readiness.reopen_task(db_session, admin, task.id)
        evidence = await _upload(db_session, actor, task)

        assert evidence.status is EvidenceStatus.PENDING

    async def test_a_passed_task_can_be_reopened_as_the_dispute_path(
        self, db_session: AsyncSession
    ) -> None:
        """Otherwise correcting a false pass needs a database edit."""
        user, actor = await _founder(db_session)
        task = await _task_for(db_session, user, actor)
        task.status = TaskStatus.PASSED
        await db_session.flush()
        _, admin = await _founder(db_session, role=Role.ADMIN)

        reopened = await readiness.reopen_task(db_session, admin, task.id)

        assert reopened.status is TaskStatus.OPEN
