"""Resubmitting a failed audit actually retries it (T2.8 follow-up).

Three separate places promise a founder that resubmitting is how a failed run is
retried -- `AuditStatus.FAILED`'s docstring, the founder-facing failure message,
and `CLIENTS.md` section 5a. None of it was true: `_redispatch_if_stranded` only
re-queued a run that was `queued` with zero attempts, so a `failed` run was found
by fingerprint and handed back unchanged with `200` forever. The only escape was
editing the profile to change the fingerprint.

The suite stayed green through it because nothing asserted the *documented*
behaviour -- the tests checked the row and the response schema, both of which
were correct for a run that simply never moved.

What is under test here is the retry and the two ways it could be worse than the
bug it replaces:

* **It must not become an unbounded re-bill.** An audit is the most expensive
  call the platform makes (D16); a founder holding down submit against a
  provider outage would otherwise buy a full `claude-opus-5` pass each time,
  which is the double-spend D14 exists to prevent.
* **A dispatch that fails must not strand the run somewhere unreachable.** The
  reset commits before the enqueue, so an enqueue that raises would leave the
  row `queued` with `attempts > 0` -- a state neither branch of
  `_requeue_if_retryable` can repair, invented by the fix for the original
  stranding.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import AccountStatus, CurrentUser, Role
from app.modules.audit import service as audit
from app.modules.audit.models import AuditRun
from app.modules.audit.repository import AuditRunRepository
from app.modules.audit.runs import LEASE_SECONDS, AuditStatus
from app.modules.identity import service as identity
from app.modules.identity.models import User
from app.modules.intake import service as intake
from app.modules.intake.fields import Stage
from app.workers.queue import QueueUnavailableError
from tests.conftest import requires_database

pytestmark = [requires_database, pytest.mark.integration]

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-signing-key-at-least-32-characters")
    monkeypatch.setenv("ARGON2_MEMORY_COST_KIB", "8192")
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def dispatched(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    """Record every dispatch instead of making one.

    Patched on `audit.service`, not `workers.queue`: the service imported the
    name at module load, so rebinding the source would not reach it.
    """
    calls: list[uuid.UUID] = []
    monkeypatch.setattr(audit, "enqueue_audit", calls.append)
    return calls


_AUDITABLE = {
    "description": {"value": "Last-mile delivery for Lagos pharmacies."},
    "business_model": {"value": "Per-delivery fee plus a subscription."},
    "team_size": {"value": 10},
    "monthly_revenue_minor": {"value": 5_000_000},
    "monthly_costs_minor": {"value": 4_000_000},
    "cash_on_hand_minor": {"value": 20_000_000},
}


async def _actor(session: AsyncSession) -> CurrentUser:
    user: User | None = await identity.register_user(
        session,
        email=f"user-{uuid.uuid4().hex}@example.test",
        password=PASSWORD,
        role=Role.FOUNDER,
        first_name="Ada",
        last_name="Tester",
    )
    assert user is not None
    user.status = AccountStatus.ACTIVE
    await session.flush()
    return CurrentUser(
        id=user.id,
        role=user.role,
        status=AccountStatus.ACTIVE,
        email_verified=True,
        mfa_enabled=user.mfa_enabled,
    )


async def _failed_run(
    session: AsyncSession, actor: CurrentUser, *, attempts: int = 1
) -> tuple[uuid.UUID, AuditRun]:
    """A profile whose only run has failed the way the worker would leave it."""
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
    run, created = await audit.request_audit(session, actor, profile.id)
    assert created

    run.status = AuditStatus.FAILED
    run.attempts = attempts
    run.error_code = "audit_failed"
    run.error_message = "The audit could not be completed."
    await session.flush()
    return profile.id, run


async def _queued_run(
    session: AsyncSession, actor: CurrentUser
) -> tuple[uuid.UUID, AuditRun]:
    """A profile with one freshly queued run, as `request_audit` leaves it."""
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
    run, created = await audit.request_audit(session, actor, profile.id)
    assert created
    return profile.id, run


# ---------------------------------------------------------------------------
# The atomic claim -- the only thing standing between a redelivery and a
# second `claude-opus-5` bill for one verdict
# ---------------------------------------------------------------------------


async def test_only_one_of_two_deliveries_can_claim_a_run(
    db_session: AsyncSession, dispatched: list[uuid.UUID]
) -> None:
    """The double-bill, asserted against real Postgres rather than reasoned about.

    RQ does not dedupe by `job_id` -- `enqueue` overwrites the hash and re-pushes
    the id -- so two deliveries of the same job genuinely reach the worker. The
    old code read the row, checked it was not `succeeded`, then marked it
    running; both passed and both ran the pipeline. One conditional UPDATE
    cannot be got through twice.
    """
    actor = await _actor(db_session)
    _, run = await _queued_run(db_session, actor)
    repository = AuditRunRepository(db_session)

    first = await repository.claim(run.id)
    second = await repository.claim(run.id)

    assert first is True
    assert second is False, "the second delivery would have billed a second audit"


async def test_a_succeeded_run_cannot_be_claimed_at_all(
    db_session: AsyncSession, dispatched: list[uuid.UUID]
) -> None:
    """Re-scoring a finished audit re-bills it and can change the verdict."""
    actor = await _actor(db_session)
    _, run = await _queued_run(db_session, actor)
    run.status = AuditStatus.SUCCEEDED
    await db_session.flush()

    assert await AuditRunRepository(db_session).claim(run.id) is False


async def test_a_stranded_running_run_can_be_reclaimed_once_its_lease_expires(
    db_session: AsyncSession, dispatched: list[uuid.UUID]
) -> None:
    """The run with no terminal state and no owner, given one.

    Before the lease this row polled for ever: RQ had released the `job_id`
    without writing anything, so no worker would touch it and every
    resubmission returned it unchanged.
    """
    actor = await _actor(db_session)
    _, run = await _queued_run(db_session, actor)
    run.status = AuditStatus.RUNNING
    run.started_at = datetime.now(UTC) - timedelta(seconds=LEASE_SECONDS + 60)
    await db_session.flush()

    assert await AuditRunRepository(db_session).claim(run.id) is True


async def test_a_worker_still_inside_its_lease_keeps_its_claim(
    db_session: AsyncSession, dispatched: list[uuid.UUID]
) -> None:
    """The failure mode a too-short lease would introduce: robbing a live worker."""
    actor = await _actor(db_session)
    _, run = await _queued_run(db_session, actor)
    run.status = AuditStatus.RUNNING
    run.started_at = datetime.now(UTC) - timedelta(seconds=LEASE_SECONDS - 60)
    await db_session.flush()

    assert await AuditRunRepository(db_session).claim(run.id) is False


async def test_resubmitting_a_stranded_run_puts_a_job_back_on_the_queue(
    db_session: AsyncSession, dispatched: list[uuid.UUID]
) -> None:
    """End to end: the founder's resubmission is what rescues a stranded run.

    No state change is expected -- the row is already claimable, all that was
    missing is a job.
    """
    actor = await _actor(db_session)
    startup_id, run = await _queued_run(db_session, actor)
    run.status = AuditStatus.RUNNING
    run.attempts = 1
    run.started_at = datetime.now(UTC) - timedelta(seconds=LEASE_SECONDS + 60)
    await db_session.flush()
    dispatched.clear()

    again, created = await audit.request_audit(db_session, actor, startup_id)

    assert again.id == run.id
    assert not created
    assert dispatched == [run.id], "a stranded run must reach the worker again"


async def test_a_live_running_run_is_not_redispatched(
    db_session: AsyncSession, dispatched: list[uuid.UUID]
) -> None:
    """Resubmitting against a working worker must change nothing."""
    actor = await _actor(db_session)
    startup_id, run = await _queued_run(db_session, actor)
    run.status = AuditStatus.RUNNING
    run.attempts = 1
    run.started_at = datetime.now(UTC)
    await db_session.flush()
    dispatched.clear()

    await audit.request_audit(db_session, actor, startup_id)

    assert dispatched == [], "re-dispatching here would bill the audit twice"


async def test_resubmitting_a_failed_run_requeues_it_under_the_same_id(
    db_session: AsyncSession, dispatched: list[uuid.UUID]
) -> None:
    """The documented retry path, which `_redispatch_if_stranded` never took."""
    actor = await _actor(db_session)
    startup_id, run = await _failed_run(db_session, actor)
    original_id = run.id
    dispatched.clear()

    again, created = await audit.request_audit(db_session, actor, startup_id)

    assert again.id == original_id, "CLIENTS.md 5a: a retry reuses the run id"
    assert not created, "the run is reused, so this is a 200 not a 202"
    assert again.status is AuditStatus.QUEUED
    assert dispatched == [original_id], "the retry must actually reach the worker"


async def test_a_requeued_run_carries_no_stale_failure(
    db_session: AsyncSession, dispatched: list[uuid.UUID]
) -> None:
    """`queued` beside an `error_code` reads as failed-and-pending at once."""
    actor = await _actor(db_session)
    startup_id, _ = await _failed_run(db_session, actor)

    again, _ = await audit.request_audit(db_session, actor, startup_id)

    assert again.error_code is None
    assert again.error_message is None
    assert again.completed_at is None


async def test_the_attempt_count_survives_a_requeue(
    db_session: AsyncSession, dispatched: list[uuid.UUID]
) -> None:
    """Resetting `attempts` would uncap the retries and hide a crash loop."""
    actor = await _actor(db_session)
    startup_id, _ = await _failed_run(db_session, actor, attempts=2)

    again, _ = await audit.request_audit(db_session, actor, startup_id)

    # Both halves matter: asserting the count alone would pass against a run
    # that was never requeued at all, which is the bug this file exists for.
    assert again.status is AuditStatus.QUEUED
    assert again.attempts == 2


async def test_retries_stop_at_the_cap(
    db_session: AsyncSession, dispatched: list[uuid.UUID]
) -> None:
    """An uncapped retry is a billed `claude-opus-5` pass per button press (D14)."""
    actor = await _actor(db_session)
    startup_id, _ = await _failed_run(
        db_session, actor, attempts=audit.MAX_AUDIT_ATTEMPTS
    )
    dispatched.clear()

    again, created = await audit.request_audit(db_session, actor, startup_id)

    assert dispatched == [], "no further billed pass past the cap"
    assert not created
    assert again.status is AuditStatus.FAILED
    assert again.error_code == "audit_retries_exhausted"
    assert again.error_message is not None
    assert "support" in again.error_message


async def test_a_dispatch_failure_leaves_the_run_retryable(
    db_session: AsyncSession,
    dispatched: list[uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reset commits before the enqueue, so a raise there must not strand it.

    `queued` with `attempts > 0` matches neither branch of
    `_requeue_if_retryable`, so a run left in that state could never be repaired
    by any later submission -- a permanent stranding created by the fix for the
    original one.
    """
    actor = await _actor(db_session)
    startup_id, _ = await _failed_run(db_session, actor)

    # Only after the fixture's own dispatch: `dispatched` covers setup, and the
    # refusal is installed for the resubmission that is actually under test.
    def refuse(_run_id: uuid.UUID) -> None:
        raise QueueUnavailableError("REDIS_URL is not set")

    monkeypatch.setattr(audit, "enqueue_audit", refuse)

    again, created = await audit.request_audit(db_session, actor, startup_id)

    assert not created
    assert again.status is AuditStatus.FAILED, (
        "a run left `queued` here can never be re-dispatched again"
    )
    assert again.error_code == "audit_requeue_failed"


async def test_a_stranded_queued_run_is_still_redispatched(
    db_session: AsyncSession, dispatched: list[uuid.UUID]
) -> None:
    """The original behaviour, which the failed-run branch must not displace."""
    actor = await _actor(db_session)
    startup_id, run = await _failed_run(db_session, actor)
    run.status = AuditStatus.QUEUED
    run.attempts = 0
    run.error_code = None
    run.error_message = None
    await db_session.flush()
    dispatched.clear()

    again, _ = await audit.request_audit(db_session, actor, startup_id)

    assert dispatched == [again.id]


async def test_a_succeeded_run_is_never_requeued(
    db_session: AsyncSession, dispatched: list[uuid.UUID]
) -> None:
    """The idempotency guarantee D14 exists for: one verdict, charged once."""
    actor = await _actor(db_session)
    startup_id, run = await _failed_run(db_session, actor)
    run.status = AuditStatus.SUCCEEDED
    run.report = {"rubric_version": "v1"}
    await db_session.flush()
    dispatched.clear()

    again, created = await audit.request_audit(db_session, actor, startup_id)

    assert dispatched == []
    assert not created
    assert again.status is AuditStatus.SUCCEEDED
