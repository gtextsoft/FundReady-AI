"""T2.8: the worker handler, against a real database and a fake model.

The queue transport is not under test -- RQ resolving a dotted path is RQ's
problem. What is under test is everything the transport cannot guarantee, and
the first one is the expensive one:

* **A completed run is never scored twice.** The unique constraint stops a
  second *row*; it does nothing about the same row being handed to a second
  worker after a visibility timeout. Re-running would re-bill the platform's
  most expensive call (D16) and could return a different verdict for identical
  inputs, which is precisely what T2.9 asserts cannot happen.
* **A failure is recorded, not raised.** Letting it propagate puts the job on
  RQ's failed queue for an automatic retry, and every retry of an audit is
  another billed pass over the same evidence.
* **The founder-facing failure text carries nothing an engineer would want.**
  `error_message` is read back over the API (`CLAUDE.md` section 4).
"""

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import AccountStatus, Role
from app.modules.audit.models import AuditRun
from app.modules.audit.runs import AuditStatus
from app.modules.identity.models import User
from app.modules.intake.models import StartupProfile
from app.workers import tasks
from tests.conftest import requires_database
from tests.unit.test_ai_client import _FakeAnthropic, _Message  # noqa: PLC2701

pytestmark = [requires_database, pytest.mark.integration]


@pytest.fixture(autouse=True)
def ai_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _assessment() -> str:
    """One scored dimension. The pipeline pads the rest as unassessed."""
    return json.dumps(
        {
            "rubric_version": "v1",
            "scores": [
                {
                    "dimension": "financial_health",
                    "score": 71,
                    "rationale": "Costs are covered by revenue on the figures given.",
                    "unmet_criteria": [],
                    "benchmark_used": None,
                    "sufficiency": "sufficient",
                    "citations": [
                        {"source_id": "startup_profile", "quote": "revenue 5000000"}
                    ],
                }
            ],
        }
    )


_AUDITABLE: dict[str, Any] = {
    "description": {"value": "Last-mile delivery for Lagos pharmacies."},
    "business_model": {"value": "Per-delivery fee."},
    "team_size": {"value": 10},
    "monthly_revenue_minor": {"value": 5_000_000},
    "monthly_costs_minor": {"value": 4_000_000},
    "cash_on_hand_minor": {"value": 20_000_000},
}


async def _queued_run(session: AsyncSession) -> AuditRun:
    user = User(
        email=f"founder-{uuid.uuid4()}@example.test",
        password_hash="not-a-real-hash",
        role=Role.FOUNDER,
        status=AccountStatus.ACTIVE,
    )
    session.add(user)
    await session.flush()

    profile = StartupProfile(
        owner_id=user.id,
        name="Kanmi Logistics",
        sector="last-mile delivery",
        country="NG",
        currency="NGN",
        fields=dict(_AUDITABLE),
    )
    session.add(profile)
    await session.flush()

    run = AuditRun(
        startup_id=profile.id,
        owner_id=user.id,
        rubric_version="v1",
        input_hash=uuid.uuid4().hex * 2,
        status=AuditStatus.QUEUED,
    )
    session.add(run)
    await session.flush()
    return run


class _BorrowedSession:
    """Hands out the test's session and declines to close it.

    The handler opens its own sessions -- a job has no request to borrow one
    from -- so left alone it would connect outside the transaction `db_session`
    rolls back and leave rows behind on a real database. Lending the test's
    session keeps every write inside that transaction; the handler's `commit()`
    calls stay real because `db_session` joins as a savepoint.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


@pytest.fixture
def worker_session(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncSession:
    monkeypatch.setattr(
        tasks, "get_session_factory", lambda: lambda: _BorrowedSession(db_session)
    )
    return db_session


def _fake_ai(monkeypatch: pytest.MonkeyPatch, responses: list[Any]) -> None:
    import app.ai.client as ai_client

    original = ai_client.AiClient

    def build(settings: Any, **kwargs: Any) -> Any:
        return original(settings, client=_FakeAnthropic(responses))

    monkeypatch.setattr(ai_client, "AiClient", build)


async def test_a_queued_run_is_scored_and_stored(
    worker_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = await _queued_run(worker_session)
    _fake_ai(monkeypatch, [_Message(_assessment())])

    await tasks.run_audit_async(run.id)
    await worker_session.refresh(run)

    assert run.status is AuditStatus.SUCCEEDED
    assert run.attempts == 1
    assert run.completed_at is not None
    assert run.report is not None
    assert run.report["rubric_version"] == "v1"
    # A Decimal, stored as a string. Coerced to a float it would no longer be
    # the score that was computed.
    assert isinstance(run.report["data_integrity_score"], str)


async def test_a_completed_run_is_never_scored_again(
    worker_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The expensive case: a redelivered job must not re-bill the audit."""
    run = await _queued_run(worker_session)
    run.status = AuditStatus.SUCCEEDED
    run.report = {"rubric_version": "v1"}
    await worker_session.flush()

    # No responses queued: any model call raises IndexError on the fake, which
    # is a louder failure than an assertion after the fact.
    _fake_ai(monkeypatch, [])

    await tasks.run_audit_async(run.id)
    await worker_session.refresh(run)

    assert run.attempts == 0, "a completed run must not be claimed again"
    assert run.report == {"rubric_version": "v1"}


async def test_a_failure_is_recorded_rather_than_raised(
    worker_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Raising would hand the job back to RQ, and every retry is billed again."""
    run = await _queued_run(worker_session)

    async def explode(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("the provider is down")

    monkeypatch.setattr(tasks, "_score", explode)

    await tasks.run_audit_async(run.id)
    await worker_session.refresh(run)

    assert run.status is AuditStatus.FAILED
    assert run.error_code == "audit_failed"
    assert run.attempts == 1, "the attempt still happened and must be visible"


async def test_the_failure_message_says_nothing_an_engineer_would_want(
    worker_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`error_message` is read back over the API (`CLAUDE.md` section 4)."""
    run = await _queued_run(worker_session)

    async def explode(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("psycopg.OperationalError at 10.0.0.4:5432, key sk-ant-xyz")

    monkeypatch.setattr(tasks, "_score", explode)

    await tasks.run_audit_async(run.id)
    await worker_session.refresh(run)

    assert run.error_message is not None
    for leak in ("psycopg", "10.0.0.4", "sk-ant", "Traceback"):
        assert leak not in run.error_message


async def test_a_run_whose_profile_vanished_fails_cleanly(
    worker_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = await _queued_run(worker_session)
    _fake_ai(monkeypatch, [])
    monkeypatch.setattr(tasks, "_snapshot_for", _none)

    await tasks.run_audit_async(run.id)
    await worker_session.refresh(run)

    assert run.status is AuditStatus.FAILED
    assert run.error_code == "profile_missing"


async def _none(*_args: Any, **_kwargs: Any) -> None:
    return None


async def test_an_unknown_run_id_is_a_no_op(
    worker_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A job for a deleted run must not crash the worker."""
    _fake_ai(monkeypatch, [])

    await tasks.run_audit_async(uuid.uuid4())


async def test_a_failure_before_the_model_call_is_recorded_too(
    worker_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `try` used to start after the database work, and that was worse.

    `assemble_benchmark_context` runs between `mark_running` and its `commit`,
    so a raise there unwound the session before either was written: the row went
    back to `queued` with zero attempts, the exception reached RQ's failed queue,
    and the founder polled `queued` with no error ever recorded. Resubmitting
    matched the stranded-run branch and dispatched the same failure again, with
    no terminal state and no `error_code` at any point.

    **`attempts` is deliberately not asserted, because this fixture cannot see
    it.** In production the failure unwinds the session before `mark_running`'s
    commit, so the increment rolls back and a run that never reached the model
    does not consume one of its retries. `_BorrowedSession` lends the test's
    session and declines to close it, so nothing is rolled back here and the
    increment survives -- the opposite of the real behaviour. Anyone adding an
    `attempts` assertion to this test is asserting the fixture, not the handler.
    """
    run = await _queued_run(worker_session)
    _fake_ai(monkeypatch, [])

    async def explode(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("Neon dropped the connection")

    monkeypatch.setattr(tasks, "assemble_benchmark_context", explode)

    await tasks.run_audit_async(run.id)
    await worker_session.refresh(run)

    assert run.status is AuditStatus.FAILED, "a pre-scoring failure is still a failure"
    assert run.error_code == "audit_failed"
    assert run.error_message is not None


async def test_recording_a_failure_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recorder runs inside `except`, and the thing that failed may be the DB.

    An exception raised from an `except` block propagates out of the handler and
    onto RQ's failed queue for an automatic retry -- the one outcome this
    handler's docstring promises never happens, and every retry of an audit is
    another billed pass.
    """

    def broken_factory() -> None:
        raise RuntimeError("the database is gone")

    monkeypatch.setattr(tasks, "get_session_factory", lambda: broken_factory)

    await tasks._record_failure(uuid.uuid4())  # noqa: SLF001 - the guarantee under test
