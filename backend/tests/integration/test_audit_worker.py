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


def _assessment_with_gaps() -> str:
    """One weak dimension and one strong one, each with an unmet criterion.

    The happy-path fixture above deliberately has no unmet criteria, so it
    produces an empty action plan and would prove nothing about T3.1.
    """
    return json.dumps(
        {
            "rubric_version": "v1",
            "scores": [
                {
                    "dimension": "financial_health",
                    "score": 30,
                    "rationale": "Burn is not accounted for.",
                    "unmet_criteria": ["State the runway and what it assumes."],
                    "benchmark_used": None,
                    "sufficiency": "sufficient",
                    "citations": [
                        {"source_id": "startup_profile", "quote": "revenue 5000000"}
                    ],
                },
                {
                    "dimension": "team",
                    "score": 95,
                    "rationale": "Experienced founders.",
                    "unmet_criteria": ["Name a second technical hire."],
                    "benchmark_used": None,
                    "sufficiency": "sufficient",
                    "citations": [
                        {"source_id": "startup_profile", "quote": "team_size 10"}
                    ],
                },
            ],
        }
    )


async def test_a_succeeded_run_generates_readiness_tasks(
    worker_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T3.1's wiring, which no unit test can see.

    `generate_for_report` is proven on its own elsewhere. What is proven here is
    that the worker actually calls it -- the composition, not the component.
    Before this the action plan was stored in JSONB and reached nothing a
    founder could act on, and every test in both suites stayed green.
    """
    from app.modules.readiness.generation import Requirement, TaskStatus
    from app.modules.readiness.repository import ReadinessTaskRepository

    run = await _queued_run(worker_session)
    _fake_ai(monkeypatch, [_Message(_assessment_with_gaps())])

    await tasks.run_audit_async(run.id)
    await worker_session.refresh(run)
    assert run.status is AuditStatus.SUCCEEDED

    stored, total = await ReadinessTaskRepository(worker_session).list_for_startup(
        run.startup_id
    )
    by_action = {task.action: task for task in stored}

    assert total == 2, "both unmet criteria should have become tasks"
    assert by_action["State the runway and what it assumes."].requirement is (
        Requirement.REQUIRED
    )
    assert by_action["Name a second technical hire."].requirement is (
        Requirement.RECOMMENDED
    )
    assert all(task.status is TaskStatus.OPEN for task in stored)
    assert all(task.audit_run_id == run.id for task in stored)
    assert all(task.owner_id == run.owner_id for task in stored)


async def test_a_failed_run_generates_no_tasks(
    worker_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tasks and the report commit together, so a failure produces neither.

    A founder must never be handed obligations derived from an audit that did
    not finish.
    """
    from app.modules.readiness.repository import ReadinessTaskRepository

    run = await _queued_run(worker_session)
    _fake_ai(monkeypatch, [])

    async def explode(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("the model refused")

    monkeypatch.setattr(tasks, "_score", explode)

    await tasks.run_audit_async(run.id)
    await worker_session.refresh(run)
    assert run.status is AuditStatus.FAILED

    _, total = await ReadinessTaskRepository(worker_session).list_for_startup(
        run.startup_id
    )
    assert total == 0


async def test_a_generation_failure_never_fails_the_job_or_the_report(
    worker_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The invariant the whole handler is built around, at its newest doorway.

    Task generation runs **after** the `try` that covers scoring, so a raise
    there used to propagate out of `run_audit_async` onto RQ's failed queue for
    an automatic retry -- and every retry is another billed `claude-opus-5`
    high-effort pass. Sharing the transaction with `mark_succeeded` made it
    worse: the rollback discarded a report that had already been paid for and
    left the run in `running` for the lease to recover half an hour later.

    Proven able to fail: putting generation back inside the report's
    transaction turns this red on both assertions.
    """
    from app.modules.readiness.repository import ReadinessTaskRepository

    run = await _queued_run(worker_session)
    _fake_ai(monkeypatch, [_Message(_assessment_with_gaps())])

    async def explode(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("uq_readiness_tasks_action, or anything else")

    monkeypatch.setattr(tasks.readiness, "generate_for_report", explode)

    await tasks.run_audit_async(run.id)  # must not raise
    await worker_session.refresh(run)

    assert run.status is AuditStatus.SUCCEEDED, "the paid-for verdict survives"
    assert run.report is not None, "the report is committed before generation runs"

    _, total = await ReadinessTaskRepository(worker_session).list_for_startup(
        run.startup_id
    )
    assert total == 0, "the founder has a report and an empty list, not a lost audit"


# ---------------------------------------------------------------------------
# Evidence assessment (T3.5)
# ---------------------------------------------------------------------------


def _graded(outcome: str, reason: str = "Undated screenshot.") -> str:
    return json.dumps({"outcome": outcome, "reasons": [reason], "citations": []})


async def _task_with_evidence(
    session: AsyncSession, *, files: int = 1
) -> tuple[Any, list[Any]]:
    """A founder, a profile, one open task, and `files` ready submissions."""
    from app.modules.intake.models import StartupProfile
    from app.modules.readiness.evidence import EvidenceStatus
    from app.modules.readiness.generation import Requirement, TaskStatus
    from app.modules.readiness.models import Evidence, ReadinessTask

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

    task = ReadinessTask(
        startup_id=profile.id,
        owner_id=user.id,
        dimension="traction",
        action="Publish a pricing page.",
        action_fingerprint=uuid.uuid4().hex * 2,
        requirement=Requirement.REQUIRED,
        status=TaskStatus.SUBMITTED,
    )
    session.add(task)
    await session.flush()

    rows = []
    for index in range(files):
        evidence = Evidence(
            task_id=task.id,
            owner_id=user.id,
            startup_id=profile.id,
            filename=f"proof-{index}.png",
            storage_key=f"{profile.id}/{uuid.uuid4()}",
            content_type="image/png",
            size_bytes=1024,
            status=EvidenceStatus.READY,
        )
        session.add(evidence)
        rows.append(evidence)
    await session.flush()
    return task, rows


def _fake_storage(monkeypatch: pytest.MonkeyPatch, content: bytes | None) -> None:
    """R2 is not under test here; the grading path is."""
    monkeypatch.setattr(tasks, "get_object", lambda *_a, **_k: content)


async def test_evidence_is_graded_and_the_task_moves(
    worker_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of T3.5: a task can now leave `open`.

    Until this ran, `TaskStatus.PASSED` was declared and unreachable.
    """
    from app.modules.readiness.evidence import AssessmentOutcome
    from app.modules.readiness.generation import TaskStatus

    task, rows = await _task_with_evidence(worker_session)
    _fake_storage(monkeypatch, b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    _fake_ai(monkeypatch, [_Message(_graded("pass", "The page is live and dated."))])

    await tasks.assess_evidence_async(task.id)
    await worker_session.refresh(task)
    await worker_session.refresh(rows[0])

    assert task.status is TaskStatus.PASSED
    assert task.assessment_attempts == 1
    assert rows[0].outcome is AssessmentOutcome.PASS
    assert rows[0].reasons == ["The page is live and dated."]
    assert rows[0].assessment_prompt_ref == "evidence_assessment@1"
    assert rows[0].assessed_at is not None


async def test_a_needs_more_grading_moves_the_task_and_charges_an_attempt(
    worker_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.readiness.generation import TaskStatus

    task, _ = await _task_with_evidence(worker_session)
    _fake_storage(monkeypatch, b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    _fake_ai(monkeypatch, [_Message(_graded("needs_more"))])

    await tasks.assess_evidence_async(task.id)
    await worker_session.refresh(task)

    assert task.status is TaskStatus.NEEDS_MORE
    assert task.assessment_attempts == 1


async def test_several_files_are_graded_as_one_submission(
    worker_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A screenshot plus the invoice that dates it is one attempt, not two.

    Grading them separately would fail both for being incomplete alone, and
    bill twice for the privilege.
    """
    from app.modules.readiness.evidence import AssessmentOutcome

    task, rows = await _task_with_evidence(worker_session, files=3)
    _fake_storage(monkeypatch, b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    _fake_ai(monkeypatch, [_Message(_graded("pass", "Shown and dated."))])

    await tasks.assess_evidence_async(task.id)
    await worker_session.refresh(task)

    assert task.assessment_attempts == 1
    for row in rows:
        await worker_session.refresh(row)
        assert row.outcome is AssessmentOutcome.PASS


async def test_a_redelivered_job_grades_nothing_and_spends_nothing(
    worker_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Idempotence comes from the query, not from a lease.

    `list_gradable` returns only ungraded rows, so a second delivery finds an
    empty list. An empty response list would make a second model call raise --
    which is the assertion: nothing was called.
    """
    task, _ = await _task_with_evidence(worker_session)
    _fake_storage(monkeypatch, b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    _fake_ai(monkeypatch, [_Message(_graded("pass", "Fine."))])

    await tasks.assess_evidence_async(task.id)
    await worker_session.refresh(task)
    first_attempts = task.assessment_attempts

    # No further responses queued: a second call would exhaust the fake and
    # raise, and the handler would swallow it and charge an attempt.
    await tasks.assess_evidence_async(task.id)
    await worker_session.refresh(task)

    assert task.assessment_attempts == first_attempts == 1


async def test_a_grading_failure_releases_the_task_and_charges_nothing(
    worker_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider outage is not the founder's mistake.

    It must not consume one of three attempts, must not leave the task reading
    `submitted` forever, and must not propagate -- an RQ auto-retry is another
    billed pass over the same files.
    """
    from app.modules.readiness.generation import TaskStatus

    task, rows = await _task_with_evidence(worker_session)
    _fake_storage(monkeypatch, b"\x89PNG\r\n\x1a\n" + b"0" * 64)

    async def explode(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("the provider is down")

    monkeypatch.setattr(tasks, "assess_submissions", explode)

    await tasks.assess_evidence_async(task.id)  # must not raise
    await worker_session.refresh(task)
    await worker_session.refresh(rows[0])

    assert task.status is TaskStatus.OPEN
    assert task.assessment_attempts == 0
    assert rows[0].outcome is None
    assert rows[0].error_code == "assessment_failed"


async def test_unfetchable_bytes_yield_needs_more_without_a_model_call(
    worker_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing readable is not a grading judgement -- there is nothing to grade.

    No responses are queued, so any model call would raise and the task would
    end up `open` rather than `needs_more`.
    """
    from app.modules.readiness.generation import TaskStatus

    task, _ = await _task_with_evidence(worker_session)
    _fake_storage(monkeypatch, None)
    _fake_ai(monkeypatch, [])

    await tasks.assess_evidence_async(task.id)
    await worker_session.refresh(task)

    assert task.status is TaskStatus.NEEDS_MORE
    assert task.assessment_attempts == 1
