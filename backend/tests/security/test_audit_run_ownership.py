"""Audit run ownership and what the status endpoint may say (T2.8).

`GET /v1/startups/{startup_id}/audits/{run_id}` is a textbook IDOR surface: both
ids arrive from the client and name a row belonging to exactly one founder.
`CLAUDE.md` section 7 puts these tests first, so they are here rather than folded
into an integration test of the happy path.

Three properties, and the third is the one that is easy to lose in a later edit:

* **Another founder's run is `404`, never `403`.** A 403 confirms the id exists,
  which turns the endpoint into an oracle an attacker can walk (`AUTH.md` §6).
* **The `startup_id` in the path is checked against the row**, not trusted. A
  caller must not be able to pair their own startup id with someone else's run
  id and learn from the status code that the run id is real.
* **The status response carries no report content.** The report is internal
  until a per-tier serializer exists (`CLAUDE.md` section 4), and this endpoint is
  reachable from the moment the run is created.
"""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import InvalidRequestError, NotFoundError
from app.core.security import AccountStatus, CurrentUser, Role
from app.modules.audit import service as audit
from app.modules.audit.models import AuditRun
from app.modules.audit.runs import AuditStatus
from app.modules.audit.schemas import AuditRunResponse
from app.modules.identity import service as identity
from app.modules.identity.models import User
from app.modules.intake import service as intake
from app.modules.intake.fields import Stage
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
    """Swallow dispatch. Redis is not a party to an authorization test.

    Patched on `audit.service` rather than on `workers.queue`, because the
    service imported the name at module load and rebinding the source would not
    reach it.
    """
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


# Everything `intake.missing_fields` asks for, so `request_audit` is exercised
# on its accepting path rather than short-circuiting on an incomplete profile.
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
    return profile.id, run


class TestIsolation:
    async def test_a_founder_polls_their_own_run(
        self, db_session: AsyncSession
    ) -> None:
        _, actor = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, actor)

        found = await audit.get_audit_run(db_session, actor, startup_id, run.id)

        assert found.id == run.id
        assert found.status is AuditStatus.QUEUED

    async def test_another_founders_run_is_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """404, not 403. A 403 would confirm the run id is real."""
        _, owner = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, owner)
        _, intruder = await _founder(db_session)

        with pytest.raises(NotFoundError):
            await audit.get_audit_run(db_session, intruder, startup_id, run.id)

    async def test_a_run_id_from_another_startup_is_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """The path's startup id is checked against the row, never trusted.

        Without this, a founder could pair *their own* startup id with another
        founder's run id. The ownership check would still refuse it -- but only
        after the row was loaded, and a mismatch that reached a different error
        would tell the caller the run id exists.
        """
        _, owner = await _founder(db_session)
        _, other_run = await _profile_with_run(db_session, owner)
        _, caller = await _founder(db_session)
        own_startup_id, _ = await _profile_with_run(db_session, caller)

        with pytest.raises(NotFoundError):
            await audit.get_audit_run(db_session, caller, own_startup_id, other_run.id)

    async def test_an_unknown_run_reads_the_same_as_a_forbidden_one(
        self, db_session: AsyncSession
    ) -> None:
        """Both denials must be indistinguishable, message included."""
        _, owner = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, owner)
        _, intruder = await _founder(db_session)

        with pytest.raises(NotFoundError) as forbidden:
            await audit.get_audit_run(db_session, intruder, startup_id, run.id)
        with pytest.raises(NotFoundError) as missing:
            await audit.get_audit_run(db_session, owner, startup_id, uuid.uuid4())

        assert str(forbidden.value) == str(missing.value)

    async def test_an_admin_reads_any_run(self, db_session: AsyncSession) -> None:
        """SACI reads across tenants by design (`AUTH.md` §2)."""
        _, owner = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, owner)
        _, admin = await _founder(db_session, role=Role.ADMIN)

        found = await audit.get_audit_run(db_session, admin, startup_id, run.id)

        assert found.id == run.id

    async def test_a_founder_cannot_queue_an_audit_of_another_startup(
        self, db_session: AsyncSession
    ) -> None:
        """Submitting is a write against someone else's data if it is not checked."""
        _, owner = await _founder(db_session)
        startup_id, _ = await _profile_with_run(db_session, owner)
        _, intruder = await _founder(db_session)

        with pytest.raises(NotFoundError):
            await audit.request_audit(db_session, intruder, startup_id)


class TestResponseContents:
    async def test_the_status_response_cannot_carry_the_report(self) -> None:
        """The report is internal until a per-tier serializer exists (§4).

        Asserted against the schema rather than one response, so a later field
        added to `AuditRunResponse` fails here rather than shipping a full
        internal report to every founder polling their audit.
        """
        assert "report" not in AuditRunResponse.model_fields

    async def test_a_populated_report_still_does_not_reach_the_caller(
        self, db_session: AsyncSession
    ) -> None:
        """The end-to-end version of the check above, on a run that has one."""
        _, actor = await _founder(db_session)
        startup_id, run = await _profile_with_run(db_session, actor)
        run.report = {"fundability": {"level": "ready"}, "secret": "internal note"}
        run.status = AuditStatus.SUCCEEDED
        await db_session.flush()

        found = await audit.get_audit_run(db_session, actor, startup_id, run.id)
        serialised = AuditRunResponse.model_validate(found).model_dump()

        assert "internal note" not in str(serialised)
        assert "report" not in serialised


class TestIdempotency:
    async def test_submitting_twice_returns_the_same_run(
        self, db_session: AsyncSession
    ) -> None:
        """D14: one set of inputs, one audit, one charge."""
        _, actor = await _founder(db_session)
        startup_id, first = await _profile_with_run(db_session, actor)

        second, created = await audit.request_audit(db_session, actor, startup_id)

        assert not created
        assert second.id == first.id

    async def test_an_incomplete_profile_is_refused_before_it_costs_anything(
        self, db_session: AsyncSession
    ) -> None:
        """`insufficient_data` is an answer a founder can have for free."""
        _, actor = await _founder(db_session)
        profile = await intake.create_profile(
            session=db_session,
            actor=actor,
            payload={"name": "Thin Co", "sector": "fintech"},
        )

        with pytest.raises(InvalidRequestError) as refused:
            await audit.request_audit(db_session, actor, profile.id)

        assert "missing_fields" in str(refused.value.details)
