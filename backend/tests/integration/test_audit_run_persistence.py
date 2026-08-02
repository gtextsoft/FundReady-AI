"""T2.8: the idempotency constraint, proven against a real database.

`test_audit_runs.py` proves the fingerprint is stable. That is necessary and not
sufficient: a stable key means nothing unless the database actually refuses the
second row. DECISIONS.md D14 is enforced by `uq_audit_runs_idempotency`, and
until an `IntegrityError` is observed, that guarantee exists only as prose in a
model docstring and a hand-written migration.

Why the constraint and not just the queue: an RQ `job_id` prevents a duplicate
only while a job is *in flight*, and the id is released the moment it finishes.
Every retry after that is stopped here or not at all.
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AccountStatus, Role
from app.modules.audit.models import AuditRun
from app.modules.audit.runs import AuditStatus
from app.modules.identity.models import User
from app.modules.intake.models import StartupProfile
from tests.conftest import requires_database

pytestmark = [requires_database, pytest.mark.integration]

HASH_A = "a" * 64
HASH_B = "b" * 64


async def _profile(session: AsyncSession) -> StartupProfile:
    """A committed founder + profile for the foreign keys to point at.

    Rolled back wholesale by `db_session`, so nothing here outlives the test.
    """
    user = User(
        email=f"founder-{uuid.uuid4()}@example.test",
        password_hash="not-a-real-hash",
        role=Role.FOUNDER,
        status=AccountStatus.ACTIVE,
    )
    session.add(user)
    await session.flush()

    profile = StartupProfile(owner_id=user.id, name="Test Co", fields={})
    session.add(profile)
    await session.flush()
    return profile


def _run(profile: StartupProfile, *, input_hash: str, rubric: str = "v1") -> AuditRun:
    return AuditRun(
        startup_id=profile.id,
        owner_id=profile.owner_id,
        rubric_version=rubric,
        input_hash=input_hash,
    )


async def test_a_duplicate_run_is_refused_by_the_database(
    db_session: AsyncSession,
) -> None:
    """The core D14 guarantee: one audit, one charge, one verdict.

    A founder double-tapping submit, a retried RQ job, and a worker that died
    mid-run all arrive here as the same insert. The database is the only thing
    still saying no once the job id has lapsed.
    """
    profile = await _profile(db_session)
    db_session.add(_run(profile, input_hash=HASH_A))
    await db_session.flush()

    db_session.add(_run(profile, input_hash=HASH_A))

    with pytest.raises(IntegrityError, match="uq_audit_runs_idempotency"):
        await db_session.flush()


async def test_rubric_version_is_redundant_in_the_constraint_by_design(
    db_session: AsyncSession,
) -> None:
    """Documents a state production cannot actually reach, and why it is kept.

    `input_fingerprint` already hashes `rubric_version` into `input_hash`, so a
    new rubric always changes the hash and the constraint's third column
    discriminates nothing. **The D12 property that matters is proven in
    `tests/unit/test_audit_runs.py::test_a_new_rubric_version_changes_the_hash`,
    not here** -- this only pins the belt-and-braces behaviour.

    It is kept in the constraint deliberately: if the fingerprint's inputs are
    ever changed and `rubric_version` is dropped from the hashed payload, this
    column is what stops a v2 audit silently reusing a v1 verdict. Cheap
    insurance against a one-line edit in a different file.
    """
    profile = await _profile(db_session)
    db_session.add(_run(profile, input_hash=HASH_A, rubric="v1"))
    await db_session.flush()

    db_session.add(_run(profile, input_hash=HASH_A, rubric="v2"))
    await db_session.flush()  # must not raise


async def test_changed_inputs_are_allowed_for_the_same_rubric(
    db_session: AsyncSession,
) -> None:
    """A founder who fixes their data must get a fresh audit, not the cache."""
    profile = await _profile(db_session)
    db_session.add(_run(profile, input_hash=HASH_A))
    await db_session.flush()

    db_session.add(_run(profile, input_hash=HASH_B))
    await db_session.flush()  # must not raise


async def test_a_new_run_starts_queued_with_no_report_and_no_attempts(
    db_session: AsyncSession,
) -> None:
    """Defaults are load-bearing: `queued` is what the status endpoint returns
    before a worker exists at all, and `report` must be absent rather than an
    empty object a client could mistake for a finished audit."""
    profile = await _profile(db_session)
    run = _run(profile, input_hash=HASH_A)
    db_session.add(run)
    await db_session.flush()
    await db_session.refresh(run)

    assert run.status is AuditStatus.QUEUED
    assert run.attempts == 0
    assert run.report is None
    assert run.started_at is None
    assert run.completed_at is None
    assert run.created_at is not None
