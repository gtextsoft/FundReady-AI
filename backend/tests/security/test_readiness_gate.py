"""The investor-visibility gate (T3.6).

PRD section 4.2: a startup becomes investor-visible when the audit clears **and**
all required tasks pass. This file is the proof, and it is a security file rather
than a feature file because the thing being kept out is an investor looking at a
business that has not earned the exposure.

**The gate is tested at the read, not at `publish`.** Consent and eligibility go
stale on different schedules: a founder eligible when they published stops being
eligible the moment a re-audit raises a new required gap, and a check written at
publish time would leave them discoverable anyway. So every test here drives
discovery and asks what an investor can actually see.

The sharpest case is `test_a_failed_task_the_audit_no_longer_raises_does_not_strand`.
It is the one a naive predicate gets wrong, it locks a founder out permanently
with no self-service path, and nothing else in the suite would notice.
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
from app.modules.audit.runs import AuditStatus
from app.modules.identity import service as identity
from app.modules.identity.models import User
from app.modules.intake import service as intake
from app.modules.intake.fields import Stage
from app.modules.investor import service as investor
from app.modules.investor.schemas import DiscoveryFilters
from app.modules.readiness import service as readiness
from app.modules.readiness.generation import Requirement, TaskStatus
from app.modules.readiness.models import ReadinessTask
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
def no_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit, "enqueue_audit", lambda _run_id: None)


def _actor(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        role=user.role,
        status=AccountStatus.ACTIVE,
        email_verified=True,
        mfa_enabled=user.mfa_enabled,
    )


async def _user(
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

_REPORT = {
    "rubric_version": "v1",
    "data_integrity_score": "100",
    "findings": [],
    "action_plan": [],
    "fundability": {
        "scope": "fundability",
        "level": "ready",
        "score": 80,
        "sufficiency": "sufficient",
        "evidenced_dimensions": [],
        "unevidenced_dimensions": [],
        "rationale": "Scored 80 out of 100 across all assessed areas.",
    },
    "saleability": {
        "scope": "saleability",
        "level": "ready",
        "score": 78,
        "sufficiency": "sufficient",
        "evidenced_dimensions": [],
        "unevidenced_dimensions": [],
        "rationale": "Scored 78 out of 100 across all assessed areas.",
    },
}


async def _published_startup(
    session: AsyncSession,
) -> tuple[User, CurrentUser, uuid.UUID, AuditRun]:
    """A founder who has opted in and has one succeeded audit. No tasks yet."""
    user, actor = await _user(session)
    profile = await intake.create_profile(
        session,
        actor,
        {
            "name": f"Kanmi {uuid.uuid4().hex[:6]}",
            "sector": "last-mile delivery",
            "stage": Stage.SEED,
            "country": "NG",
            "currency": "NGN",
            "fields": dict(_AUDITABLE),
        },
    )
    run = AuditRun(
        startup_id=profile.id,
        owner_id=user.id,
        rubric_version="v1",
        input_hash=uuid.uuid4().hex * 2,
        status=AuditStatus.SUCCEEDED,
        report=dict(_REPORT),
    )
    session.add(run)
    await session.flush()
    await intake.set_discoverability(session, actor, profile.id, visible=True)
    return user, actor, profile.id, run


def _task(
    *,
    startup_id: uuid.UUID,
    owner_id: uuid.UUID,
    run_id: uuid.UUID | None,
    requirement: Requirement = Requirement.REQUIRED,
    status: TaskStatus = TaskStatus.OPEN,
) -> ReadinessTask:
    return ReadinessTask(
        startup_id=startup_id,
        owner_id=owner_id,
        audit_run_id=run_id,
        dimension="traction",
        action=f"Do the thing {uuid.uuid4().hex[:8]}.",
        action_fingerprint=uuid.uuid4().hex * 2,
        requirement=requirement,
        status=status,
    )


async def _discovers(
    session: AsyncSession, actor: CurrentUser, startup_id: uuid.UUID
) -> bool:
    """Whether this startup is reachable through discovery at all."""
    page = await investor.discover(
        session, actor, DiscoveryFilters(), limit=100, offset=0
    )
    return any(card.startup_id == startup_id for card in page.items)


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


class TestGate:
    async def test_a_cleared_startup_is_discoverable(
        self, db_session: AsyncSession
    ) -> None:
        """The control. Without it the rest could pass by filtering everything out."""
        _, _, startup_id, _ = await _published_startup(db_session)
        _, seeker = await _user(db_session, role=Role.INVESTOR)

        assert await _discovers(db_session, seeker, startup_id)

    async def test_one_open_required_task_hides_the_startup(
        self, db_session: AsyncSession
    ) -> None:
        """The whole point of T3.6.

        Before this, a startup scoring 20 with every required task outstanding
        was discoverable the moment its founder pressed publish.
        """
        user, _, startup_id, run = await _published_startup(db_session)
        db_session.add(_task(startup_id=startup_id, owner_id=user.id, run_id=run.id))
        await db_session.flush()
        _, seeker = await _user(db_session, role=Role.INVESTOR)

        assert not await _discovers(db_session, seeker, startup_id)

    async def test_passing_the_last_required_task_restores_visibility(
        self, db_session: AsyncSession
    ) -> None:
        user, _, startup_id, run = await _published_startup(db_session)
        task = _task(startup_id=startup_id, owner_id=user.id, run_id=run.id)
        db_session.add(task)
        await db_session.flush()
        _, seeker = await _user(db_session, role=Role.INVESTOR)
        assert not await _discovers(db_session, seeker, startup_id)

        task.status = TaskStatus.PASSED
        await db_session.flush()

        assert await _discovers(db_session, seeker, startup_id)

    @pytest.mark.parametrize(
        "status",
        [
            TaskStatus.OPEN,
            TaskStatus.SUBMITTED,
            TaskStatus.FAILED,
            TaskStatus.NEEDS_MORE,
        ],
    )
    async def test_every_unpassed_state_blocks(
        self, db_session: AsyncSession, status: TaskStatus
    ) -> None:
        """Only `passed` clears it.

        `submitted` is the one worth stating: evidence being *graded* is not
        evidence having *passed*, and treating it as good enough would let a
        founder become visible for the minute a grading takes.
        """
        user, _, startup_id, run = await _published_startup(db_session)
        db_session.add(
            _task(
                startup_id=startup_id,
                owner_id=user.id,
                run_id=run.id,
                status=status,
            )
        )
        await db_session.flush()
        _, seeker = await _user(db_session, role=Role.INVESTOR)

        assert not await _discovers(db_session, seeker, startup_id)

    async def test_a_recommended_task_does_not_block(
        self, db_session: AsyncSession
    ) -> None:
        """`recommended` has to be genuinely optional or the distinction is noise."""
        user, _, startup_id, run = await _published_startup(db_session)
        db_session.add(
            _task(
                startup_id=startup_id,
                owner_id=user.id,
                run_id=run.id,
                requirement=Requirement.RECOMMENDED,
            )
        )
        await db_session.flush()
        _, seeker = await _user(db_session, role=Role.INVESTOR)

        assert await _discovers(db_session, seeker, startup_id)

    async def test_an_obsolete_required_task_does_not_block(
        self, db_session: AsyncSession
    ) -> None:
        """A gap the audit stopped raising is not work the founder owes."""
        user, _, startup_id, run = await _published_startup(db_session)
        db_session.add(
            _task(
                startup_id=startup_id,
                owner_id=user.id,
                run_id=run.id,
                status=TaskStatus.OBSOLETE,
            )
        )
        await db_session.flush()
        _, seeker = await _user(db_session, role=Role.INVESTOR)

        assert await _discovers(db_session, seeker, startup_id)

    async def test_a_failed_task_the_audit_no_longer_raises_does_not_strand(
        self, db_session: AsyncSession
    ) -> None:
        """The case a naive predicate gets wrong, and it is not recoverable.

        `_retire_unraised` retires only `OPEN` tasks, deliberately, so a founder's
        evidence is never erased -- which means a task graded `failed` keeps that
        status forever, even after a later audit stops raising the gap.

        Counting every task ever raised would leave that founder permanently
        invisible with **no self-service path**: the gap is absent from the
        current report, so no new evidence can address it, and an admin reopen
        sets it to `open`, which is still not `passed`.

        Scoping the gate to the tasks the *latest* run raised is what makes it
        mean "outstanding according to the report an investor would be shown".
        """
        user, _, startup_id, old_run = await _published_startup(db_session)

        # Graded `failed` under an audit that has since been superseded.
        db_session.add(
            _task(
                startup_id=startup_id,
                owner_id=user.id,
                run_id=old_run.id,
                status=TaskStatus.FAILED,
            )
        )
        await db_session.flush()

        # `created_at` is set explicitly: Postgres `now()` is the transaction
        # timestamp, so two runs inserted in one transaction would otherwise tie
        # and this test would be asserting how the tie breaks rather than which
        # run is newer.
        newer = AuditRun(
            startup_id=startup_id,
            owner_id=user.id,
            rubric_version="v1",
            input_hash=uuid.uuid4().hex * 2,
            status=AuditStatus.SUCCEEDED,
            report=dict(_REPORT),
            created_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        db_session.add(newer)
        await db_session.flush()

        _, seeker = await _user(db_session, role=Role.INVESTOR)

        assert await _discovers(db_session, seeker, startup_id), (
            "a gap the current report does not raise must not gate the founder"
        )

    async def test_a_task_the_newest_run_still_raises_does_block(
        self, db_session: AsyncSession
    ) -> None:
        """The other half of the same rule, so the scoping cannot be a no-op."""
        user, _, startup_id, old_run = await _published_startup(db_session)
        stale = _task(
            startup_id=startup_id,
            owner_id=user.id,
            run_id=old_run.id,
            status=TaskStatus.FAILED,
        )
        db_session.add(stale)
        await db_session.flush()

        # `created_at` is set explicitly: Postgres `now()` is the transaction
        # timestamp, so two runs inserted in one transaction would otherwise tie
        # and this test would be asserting how the tie breaks rather than which
        # run is newer.
        newer = AuditRun(
            startup_id=startup_id,
            owner_id=user.id,
            rubric_version="v1",
            input_hash=uuid.uuid4().hex * 2,
            status=AuditStatus.SUCCEEDED,
            report=dict(_REPORT),
            created_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        db_session.add(newer)
        await db_session.flush()

        # The regeneration would refresh `audit_run_id` onto the new run.
        stale.audit_run_id = newer.id
        await db_session.flush()

        _, seeker = await _user(db_session, role=Role.INVESTOR)

        assert not await _discovers(db_session, seeker, startup_id)

    async def test_consent_is_still_required_on_top_of_the_gate(
        self, db_session: AsyncSession
    ) -> None:
        """Clearing the gate does not publish anybody.

        Eligibility and consent are separate, and the gate must not become a
        back door that exposes a founder who never opted in.
        """
        _, actor, startup_id, _ = await _published_startup(db_session)
        await intake.set_discoverability(db_session, actor, startup_id, visible=False)
        _, seeker = await _user(db_session, role=Role.INVESTOR)

        assert not await _discovers(db_session, seeker, startup_id)

    async def test_publishing_stays_unconditional(
        self, db_session: AsyncSession
    ) -> None:
        """`publish` is consent, and consent is not gated on eligibility.

        Refusing it would be the stale check T3.6 exists to avoid, and it would
        also stop a founder opting in *before* finishing their tasks -- which is
        a reasonable thing to want to do once.
        """
        user, actor, startup_id, run = await _published_startup(db_session)
        db_session.add(_task(startup_id=startup_id, owner_id=user.id, run_id=run.id))
        await db_session.flush()

        profile = await intake.set_discoverability(
            db_session, actor, startup_id, visible=True
        )

        assert profile.investor_visible is True


# ---------------------------------------------------------------------------
# What the founder is told
# ---------------------------------------------------------------------------


class TestSummaryGateState:
    async def test_the_summary_agrees_with_the_gate(
        self, db_session: AsyncSession
    ) -> None:
        """If these two disagree, a founder is told something untrue."""
        user, actor, startup_id, run = await _published_startup(db_session)
        db_session.add(_task(startup_id=startup_id, owner_id=user.id, run_id=run.id))
        await db_session.flush()
        _, seeker = await _user(db_session, role=Role.INVESTOR)

        summary = await readiness.summarise_tasks(db_session, actor, startup_id)

        assert summary.required_open == 1
        assert summary.gate_cleared is False
        assert summary.discoverable is False
        assert not await _discovers(db_session, seeker, startup_id)

    async def test_a_cleared_summary_matches_a_discoverable_startup(
        self, db_session: AsyncSession
    ) -> None:
        _, actor, startup_id, _ = await _published_startup(db_session)
        _, seeker = await _user(db_session, role=Role.INVESTOR)

        summary = await readiness.summarise_tasks(db_session, actor, startup_id)

        assert summary.gate_cleared is True
        assert summary.discoverable is True
        assert await _discovers(db_session, seeker, startup_id)

    async def test_consent_and_eligibility_are_reported_separately(
        self, db_session: AsyncSession
    ) -> None:
        """Two different problems with two different fixes.

        Collapsing them would leave a founder unable to tell "you have work
        left" from "you have not opted in".
        """
        _, actor, startup_id, _ = await _published_startup(db_session)
        await intake.set_discoverability(db_session, actor, startup_id, visible=False)

        summary = await readiness.summarise_tasks(db_session, actor, startup_id)

        assert summary.gate_cleared is True, "eligible"
        assert summary.discoverable is False, "but has not opted in"

    async def test_no_audit_reports_no_gate_rather_than_a_cleared_one(
        self, db_session: AsyncSession
    ) -> None:
        """Zero outstanding tasks must not read as cleared when nothing ran.

        An empty task list and a completed task list are the same count and very
        different situations.
        """
        _, actor = await _user(db_session)
        profile = await intake.create_profile(
            db_session,
            actor,
            {
                "name": "No Audit Yet",
                "sector": "last-mile delivery",
                "stage": Stage.SEED,
                "country": "NG",
                "currency": "NGN",
                "fields": dict(_AUDITABLE),
            },
        )

        summary = await readiness.summarise_tasks(db_session, actor, profile.id)

        assert summary.has_audit is False
        assert summary.required_open == 0
        assert summary.gate_cleared is False
        assert summary.discoverable is False

    async def test_counts_are_scoped_to_the_latest_run(
        self, db_session: AsyncSession
    ) -> None:
        """A stranded `failed` task must not sit in the founder's progress bar.

        It would be a denominator that can never reach zero.
        """
        user, actor, startup_id, old_run = await _published_startup(db_session)
        db_session.add(
            _task(
                startup_id=startup_id,
                owner_id=user.id,
                run_id=old_run.id,
                status=TaskStatus.FAILED,
            )
        )
        await db_session.flush()

        # `created_at` is set explicitly: Postgres `now()` is the transaction
        # timestamp, so two runs inserted in one transaction would otherwise tie
        # and this test would be asserting how the tie breaks rather than which
        # run is newer.
        newer = AuditRun(
            startup_id=startup_id,
            owner_id=user.id,
            rubric_version="v1",
            input_hash=uuid.uuid4().hex * 2,
            status=AuditStatus.SUCCEEDED,
            report=dict(_REPORT),
            created_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        db_session.add(newer)
        await db_session.flush()

        summary = await readiness.summarise_tasks(db_session, actor, startup_id)

        assert summary.total == 0
        assert summary.required_open == 0
        assert summary.gate_cleared is True
