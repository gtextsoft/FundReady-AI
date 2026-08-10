"""The lease that gives a stranded audit run an owner again.

Two production bugs, one cause -- a row that says a job is in flight behind a
job that no longer exists:

* **A run stranded in `running` polled for ever.** RQ kills the job at
  `AUDIT_JOB_TIMEOUT` and releases the `job_id` without writing to the row, so
  a killed worker or a redeploy mid-call left `status=running` and
  `completed_at` NULL permanently. Every resubmission returned it with `200` and
  queued nothing, and `CLIENTS.md` section 5a tells the client `running` means
  keep polling.
* **A redelivered job double-billed.** The worker checked `status is SUCCEEDED`
  on a loaded row and then marked it running -- a gap two deliveries both got
  through, producing two `claude-opus-5` high-effort passes for one verdict.

The lease is deliberately twice the job timeout: shorter would be worse than
none, because it would let a second worker rob a claim from a first that is
merely slow and bill the platform's most expensive call twice.

These are the pure-logic halves, so they run in CI. The atomic UPDATE itself is
exercised against a real database in `tests/integration/test_audit_retry.py`.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.modules.audit import service
from app.modules.audit.runs import LEASE_SECONDS, AuditStatus, lease_cutoff
from app.workers.queue import AUDIT_JOB_TIMEOUT


class _Run:
    """Only the four attributes `_is_stranded` reads."""

    def __init__(
        self,
        status: AuditStatus,
        started_at: datetime | None,
        attempts: int = 1,
    ) -> None:
        self.id = uuid.uuid4()
        self.status = status
        self.started_at = started_at
        self.attempts = attempts


def _ago(seconds: float) -> datetime:
    return datetime.now(UTC) - timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# The lease itself
# ---------------------------------------------------------------------------


def test_the_lease_outlasts_the_job_timeout() -> None:
    """The margin is the safety property, not a tuning choice.

    A lease shorter than the timeout RQ enforces would let a second worker claim
    a run whose first worker is still inside a billed call.
    """
    assert LEASE_SECONDS > AUDIT_JOB_TIMEOUT


def test_the_cutoff_is_one_lease_in_the_past() -> None:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)

    assert lease_cutoff(now) == now - timedelta(seconds=LEASE_SECONDS)


# ---------------------------------------------------------------------------
# Which runs are stranded
# ---------------------------------------------------------------------------


def test_a_running_run_past_its_lease_is_stranded() -> None:
    run = _Run(AuditStatus.RUNNING, _ago(LEASE_SECONDS + 60))

    assert service._is_stranded(run) is True


def test_a_running_run_inside_its_lease_is_left_alone() -> None:
    """A worker mid-call must never be robbed of its claim -- that is a double bill."""
    run = _Run(AuditStatus.RUNNING, _ago(LEASE_SECONDS - 60))

    assert service._is_stranded(run) is False


def test_a_worker_at_the_rq_timeout_still_holds_its_claim() -> None:
    """The concrete case the margin exists for: RQ has not killed it yet."""
    run = _Run(AuditStatus.RUNNING, _ago(AUDIT_JOB_TIMEOUT - 1))

    assert service._is_stranded(run) is False


def test_a_queued_run_with_attempts_past_its_lease_is_stranded() -> None:
    """The narrower sibling: the reset committed and the dispatch was lost."""
    run = _Run(AuditStatus.QUEUED, _ago(LEASE_SECONDS + 60), attempts=1)

    assert service._is_stranded(run) is True


def test_a_never_claimed_queued_run_is_not_stranded() -> None:
    """`started_at` is NULL, so there is no lease to have expired.

    This is the "committed but never dispatched" case, which has its own repair
    path keyed on `attempts == 0`. Treating it as stranded here would make the
    two branches overlap and the reasoning about each one unreliable.
    """
    run = _Run(AuditStatus.QUEUED, None, attempts=0)

    assert service._is_stranded(run) is False


def test_a_succeeded_run_is_never_stranded() -> None:
    """However old it is. Re-dispatching a finished audit re-bills it."""
    run = _Run(AuditStatus.SUCCEEDED, _ago(LEASE_SECONDS * 10))

    assert service._is_stranded(run) is False


def test_a_failed_run_is_not_stranded_however_old() -> None:
    """`failed` has its own capped retry path; the lease must not bypass the cap.

    Without this the attempt cap would be reachable only when a founder
    resubmitted quickly, and an old failed run would re-dispatch unbounded --
    the double-spend D14 exists to prevent.
    """
    run = _Run(AuditStatus.FAILED, _ago(LEASE_SECONDS * 10), attempts=99)

    assert service._is_stranded(run) is False
