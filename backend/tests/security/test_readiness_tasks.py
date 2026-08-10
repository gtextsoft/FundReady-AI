"""Readiness task isolation and re-audit reconciliation (T3.1).

`GET /v1/startups/{startup_id}/tasks/{task_id}` is the same IDOR surface as the
audit status endpoint: both ids arrive from the client and name a row belonging
to exactly one founder. `CLAUDE.md` section 7 puts these tests first.

The second half is not a security property but is tested with the same
seriousness, because getting it wrong destroys founder data silently. **A
re-audit rewrites the entire action plan.** If generation inserted that plan
blindly, the second audit would mint a duplicate of every task and strand weeks
of the founder's evidence on rows nothing points at any more -- and the suite
would stay green, because every individual task would look correct.
"""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import Citation, DataSufficiency
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.security import AccountStatus, CurrentUser, Role
from app.modules.audit import service as audit
from app.modules.audit.models import AuditRun
from app.modules.audit.rubric.v1 import Dimension, DimensionScore
from app.modules.audit.runs import AuditStatus
from app.modules.audit.synthesis import AuditReport, synthesise
from app.modules.identity import service as identity
from app.modules.identity.models import User
from app.modules.intake import service as intake
from app.modules.intake.fields import Stage
from app.modules.readiness import service as readiness
from app.modules.readiness.generation import Requirement, TaskStatus
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
    """Redis is not a party to an authorization test."""
    monkeypatch.setattr(audit, "enqueue_audit", lambda _run_id: None)


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


async def _profile_with_run(
    session: AsyncSession, actor: CurrentUser
) -> tuple[uuid.UUID, AuditRun]:
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

    # **Marked succeeded, because a task can only exist after a run succeeds.**
    # The worker generates tasks in the block after `mark_succeeded`, so every
    # `audit_run_id` in production points at a run that produced a report. A
    # fixture that generates tasks against a `queued` run is describing a state
    # the system cannot reach -- and it hid the fact that `summarise_tasks`
    # resolves its counts against the latest *succeeded* run (T3.6).
    run.status = AuditStatus.SUCCEEDED
    run.report = {
        "rubric_version": "v1",
        "data_integrity_score": "100",
        "findings": [],
        "action_plan": [],
    }
    await session.flush()
    return profile.id, run


def _score(
    dimension: Dimension,
    value: int = 80,
    *,
    sufficiency: DataSufficiency = DataSufficiency.SUFFICIENT,
    unmet: tuple[str, ...] = (),
) -> DimensionScore:
    citations = (
        []
        if sufficiency is DataSufficiency.INSUFFICIENT_DATA
        else [Citation(source_id="deck.pdf", quote="MRR of 4.1m NGN")]
    )
    return DimensionScore(
        dimension=dimension,
        score=value,
        rationale="because the evidence says so",
        sufficiency=sufficiency,
        citations=citations,
        unmet_criteria=list(unmet),
    )


def _report(*scores: DimensionScore) -> AuditReport:
    return synthesise(rubric_version="v1", scores=list(scores))


async def _generate(
    session: AsyncSession,
    startup_id: uuid.UUID,
    owner: User,
    run: AuditRun,
    report: AuditReport,
) -> None:
    await readiness.generate_for_report(
        session,
        startup_id=startup_id,
        owner_id=owner.id,
        audit_run_id=run.id,
        report=report,
    )


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


class TestIsolation:
    async def test_a_founder_reads_their_own_tasks(
        self, db_session: AsyncSession
    ) -> None:
        user, actor = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, actor)
        await _generate(
            db_session,
            startup_id,
            user,
            run,
            _report(_score(Dimension.TRACTION, 30, unmet=("Show growth.",))),
        )

        items, total = await readiness.list_tasks(db_session, actor, startup_id)

        assert total == 1
        assert items[0].action == "Show growth."
        assert items[0].requirement is Requirement.REQUIRED

    async def test_another_founders_task_is_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """404, not 403. A 403 would confirm the task id is real."""
        owner_user, owner = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, owner)
        await _generate(
            db_session,
            startup_id,
            owner_user,
            run,
            _report(_score(Dimension.TRACTION, 30, unmet=("Show growth.",))),
        )
        items, _ = await readiness.list_tasks(db_session, owner, startup_id)

        _, intruder = await _founder(db_session)

        with pytest.raises(NotFoundError):
            await readiness.get_task(db_session, intruder, startup_id, items[0].id)

    async def test_another_founders_task_list_is_not_found(
        self, db_session: AsyncSession
    ) -> None:
        _, owner = await _founder(db_session)
        startup_id, _ = await _profile_with_run(db_session, owner)
        _, intruder = await _founder(db_session)

        with pytest.raises(NotFoundError):
            await readiness.list_tasks(db_session, intruder, startup_id)

    async def test_a_task_id_from_another_startup_is_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """The `startup_id` in the path is checked against the row, not trusted.

        Otherwise a caller pairs their own startup id with someone else's task
        id and learns from the status code that the task id is real.
        """
        other_user, other = await _founder(db_session)
        other_startup, other_run = await _profile_with_run(db_session, other)
        await _generate(
            db_session,
            other_startup,
            other_user,
            other_run,
            _report(_score(Dimension.TRACTION, 30, unmet=("Show growth.",))),
        )
        stolen, _ = await readiness.list_tasks(db_session, other, other_startup)

        caller_user, caller = await _founder(db_session)
        own_startup, _ = await _profile_with_run(db_session, caller)

        with pytest.raises(NotFoundError):
            await readiness.get_task(db_session, caller, own_startup, stolen[0].id)

    async def test_an_admin_reads_across_tenants(
        self, db_session: AsyncSession
    ) -> None:
        """SACI has full visibility on every task (PRD section 3)."""
        owner_user, owner = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, owner)
        await _generate(
            db_session,
            startup_id,
            owner_user,
            run,
            _report(_score(Dimension.TRACTION, 30, unmet=("Show growth.",))),
        )
        _, admin = await _founder(db_session, role=Role.ADMIN)

        items, total = await readiness.list_tasks(db_session, admin, startup_id)

        assert total == 1
        assert await readiness.get_task(db_session, admin, startup_id, items[0].id)

    async def test_a_missing_task_and_a_forbidden_one_answer_identically(
        self, db_session: AsyncSession
    ) -> None:
        _, actor = await _founder(db_session)
        startup_id, _ = await _profile_with_run(db_session, actor)

        with pytest.raises(NotFoundError) as absent:
            await readiness.get_task(db_session, actor, startup_id, uuid.uuid4())

        owner_user, owner = await _founder(db_session)
        other_startup, other_run = await _profile_with_run(db_session, owner)
        await _generate(
            db_session,
            other_startup,
            owner_user,
            other_run,
            _report(_score(Dimension.TRACTION, 30, unmet=("Show growth.",))),
        )
        theirs, _ = await readiness.list_tasks(db_session, owner, other_startup)

        with pytest.raises(NotFoundError) as forbidden:
            await readiness.get_task(db_session, actor, startup_id, theirs[0].id)

        assert str(absent.value) == str(forbidden.value)


# ---------------------------------------------------------------------------
# A re-audit reconciles; it never rewrites
# ---------------------------------------------------------------------------


class TestRegeneration:
    async def test_the_same_report_twice_does_not_duplicate(
        self, db_session: AsyncSession
    ) -> None:
        user, actor = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, actor)
        report = _report(_score(Dimension.TRACTION, 30, unmet=("Show growth.",)))

        await _generate(db_session, startup_id, user, run, report)
        await _generate(db_session, startup_id, user, run, report)

        _, total = await readiness.list_tasks(db_session, actor, startup_id)

        assert total == 1

    async def test_evidence_progress_survives_a_re_audit(
        self, db_session: AsyncSession
    ) -> None:
        """The whole reason regeneration reconciles rather than rewrites.

        Simulates what T3.5 will do -- move a task off `open` -- and proves the
        next audit leaves that state alone.
        """
        user, actor = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, actor)
        report = _report(_score(Dimension.TRACTION, 30, unmet=("Show growth.",)))
        await _generate(db_session, startup_id, user, run, report)

        items, _ = await readiness.list_tasks(db_session, actor, startup_id)
        items[0].status = TaskStatus.PASSED
        await db_session.flush()

        await _generate(db_session, startup_id, user, run, report)

        after, total = await readiness.list_tasks(db_session, actor, startup_id)
        assert total == 1
        assert after[0].id == items[0].id
        assert after[0].status is TaskStatus.PASSED

    async def test_severity_is_refreshed_when_a_dimension_improves(
        self, db_session: AsyncSession
    ) -> None:
        """A founder who fixed the score should stop being obliged by it."""
        user, actor = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, actor)
        action = "Show growth."

        await _generate(
            db_session,
            startup_id,
            user,
            run,
            _report(_score(Dimension.TRACTION, 30, unmet=(action,))),
        )
        before, _ = await readiness.list_tasks(db_session, actor, startup_id)
        assert before[0].requirement is Requirement.REQUIRED

        await _generate(
            db_session,
            startup_id,
            user,
            run,
            _report(_score(Dimension.TRACTION, 95, unmet=(action,))),
        )

        after, total = await readiness.list_tasks(db_session, actor, startup_id)
        assert total == 1
        assert after[0].id == before[0].id
        assert after[0].requirement is Requirement.RECOMMENDED
        assert after[0].dimension_score == 95

    async def test_an_untouched_task_the_audit_stops_raising_is_retired(
        self, db_session: AsyncSession
    ) -> None:
        user, actor = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, actor)

        await _generate(
            db_session,
            startup_id,
            user,
            run,
            _report(_score(Dimension.TRACTION, 30, unmet=("Show growth.",))),
        )
        await _generate(
            db_session,
            startup_id,
            user,
            run,
            _report(_score(Dimension.TRACTION, 30, unmet=("Publish pricing.",))),
        )

        items, _ = await readiness.list_tasks(db_session, actor, startup_id)
        by_action = {task.action: task for task in items}

        assert by_action["Show growth."].status is TaskStatus.OBSOLETE
        assert by_action["Publish pricing."].status is TaskStatus.OPEN

    async def test_a_task_carrying_evidence_is_never_retired(
        self, db_session: AsyncSession
    ) -> None:
        """A record of work a founder did is not erased by a later audit.

        `failed` is the case that looks retirable and is not: it has evidence
        attached and a founder who is owed the reason.
        """
        user, actor = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, actor)
        await _generate(
            db_session,
            startup_id,
            user,
            run,
            _report(_score(Dimension.TRACTION, 30, unmet=("Show growth.",))),
        )
        items, _ = await readiness.list_tasks(db_session, actor, startup_id)
        items[0].status = TaskStatus.FAILED
        await db_session.flush()

        await _generate(
            db_session,
            startup_id,
            user,
            run,
            _report(_score(Dimension.TRACTION, 30, unmet=("Publish pricing.",))),
        )

        after, _ = await readiness.list_tasks(db_session, actor, startup_id)
        by_action = {task.action: task for task in after}

        assert by_action["Show growth."].status is TaskStatus.FAILED

    async def test_a_retired_gap_that_comes_back_reopens(
        self, db_session: AsyncSession
    ) -> None:
        """Leaving it retired would hide a regression from the founder."""
        user, actor = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, actor)
        raised = _report(_score(Dimension.TRACTION, 30, unmet=("Show growth.",)))
        dropped = _report(_score(Dimension.TRACTION, 30, unmet=("Publish pricing.",)))

        await _generate(db_session, startup_id, user, run, raised)
        await _generate(db_session, startup_id, user, run, dropped)
        await _generate(db_session, startup_id, user, run, raised)

        items, _ = await readiness.list_tasks(db_session, actor, startup_id)
        by_action = {task.action: task for task in items}

        assert by_action["Show growth."].status is TaskStatus.OPEN

    async def test_one_founders_generation_does_not_touch_anothers_tasks(
        self, db_session: AsyncSession
    ) -> None:
        """Retirement is scoped to the startup being regenerated.

        A missing `startup_id` filter on the retire query would obsolete every
        other founder's identically-worded task on the platform, and no
        single-tenant test would see it.
        """
        first_user, first = await _founder(db_session)
        first_startup, first_run = await _profile_with_run(db_session, first)
        second_user, second = await _founder(db_session)
        second_startup, second_run = await _profile_with_run(db_session, second)

        shared = _report(_score(Dimension.TRACTION, 30, unmet=("Show growth.",)))
        await _generate(db_session, first_startup, first_user, first_run, shared)
        await _generate(db_session, second_startup, second_user, second_run, shared)

        await _generate(
            db_session,
            second_startup,
            second_user,
            second_run,
            _report(_score(Dimension.TRACTION, 30, unmet=("Publish pricing.",))),
        )

        untouched, total = await readiness.list_tasks(db_session, first, first_startup)

        assert total == 1
        assert untouched[0].status is TaskStatus.OPEN


# ---------------------------------------------------------------------------
# Listing, filtering, and the summary
# ---------------------------------------------------------------------------


class TestListing:
    async def test_priority_and_blocking_tasks_sort_first(
        self, db_session: AsyncSession
    ) -> None:
        user, actor = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, actor)
        await _generate(
            db_session,
            startup_id,
            user,
            run,
            _report(
                _score(Dimension.TEAM, 95, unmet=("Optional polish.",)),
                _score(Dimension.TRACTION, 20, unmet=("Blocking work.",)),
            ),
        )

        items, _ = await readiness.list_tasks(db_session, actor, startup_id)

        assert items[0].action == "Blocking work."

    async def test_filtering_by_requirement(self, db_session: AsyncSession) -> None:
        user, actor = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, actor)
        await _generate(
            db_session,
            startup_id,
            user,
            run,
            _report(
                _score(Dimension.TEAM, 95, unmet=("Optional polish.",)),
                _score(Dimension.TRACTION, 20, unmet=("Blocking work.",)),
            ),
        )

        items, total = await readiness.list_tasks(
            db_session, actor, startup_id, requirement=Requirement.REQUIRED
        )

        assert total == 1
        assert items[0].action == "Blocking work."

    async def test_the_total_ignores_pagination(self, db_session: AsyncSession) -> None:
        """`CLAUDE.md` section 6: a client cannot render "page N of M" without it."""
        user, actor = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, actor)
        await _generate(
            db_session,
            startup_id,
            user,
            run,
            _report(_score(Dimension.TRACTION, 20, unmet=("A.", "B.", "C."))),
        )

        items, total = await readiness.list_tasks(
            db_session, actor, startup_id, limit=1, offset=0
        )

        assert len(items) == 1
        assert total == 3

    async def test_paging_never_repeats_or_drops_a_row(
        self, db_session: AsyncSession
    ) -> None:
        """A LIMIT/OFFSET over a non-deterministic ORDER BY does both."""
        user, actor = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, actor)
        await _generate(
            db_session,
            startup_id,
            user,
            run,
            _report(_score(Dimension.TRACTION, 20, unmet=("A.", "B.", "C.", "D."))),
        )

        seen: list[uuid.UUID] = []
        for offset in range(0, 4, 2):
            page, _ = await readiness.list_tasks(
                db_session, actor, startup_id, limit=2, offset=offset
            )
            seen.extend(task.id for task in page)

        assert len(seen) == 4
        assert len(set(seen)) == 4

    async def test_the_summary_counts_what_the_gate_will_test(
        self, db_session: AsyncSession
    ) -> None:
        user, actor = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, actor)
        await _generate(
            db_session,
            startup_id,
            user,
            run,
            _report(
                _score(Dimension.TRACTION, 20, unmet=("A.", "B.")),
                _score(Dimension.TEAM, 95, unmet=("C.",)),
            ),
        )

        summary = await readiness.summarise_tasks(db_session, actor, startup_id)

        assert summary.total == 3
        assert summary.required_total == 2
        assert summary.required_open == 2
        assert summary.required_passed == 0
        assert summary.recommended_total == 1

    async def test_the_summary_excludes_retired_tasks(
        self, db_session: AsyncSession
    ) -> None:
        """A retired gap is not work the founder owes."""
        user, actor = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, actor)
        await _generate(
            db_session,
            startup_id,
            user,
            run,
            _report(_score(Dimension.TRACTION, 20, unmet=("A.",))),
        )
        await _generate(
            db_session,
            startup_id,
            user,
            run,
            _report(_score(Dimension.TRACTION, 20, unmet=("B.",))),
        )

        summary = await readiness.summarise_tasks(db_session, actor, startup_id)

        assert summary.total == 1
        assert summary.required_total == 1

    async def test_a_startup_with_no_audit_has_no_tasks(
        self, db_session: AsyncSession
    ) -> None:
        """Empty is a normal answer, not an error."""
        _, actor = await _founder(db_session)
        startup_id, _ = await _profile_with_run(db_session, actor)

        items, total = await readiness.list_tasks(db_session, actor, startup_id)
        summary = await readiness.summarise_tasks(db_session, actor, startup_id)

        assert items == []
        assert total == 0
        assert summary.total == 0
