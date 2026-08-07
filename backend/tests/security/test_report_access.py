"""Who can reach a stored audit report, and through which door (T4.2).

`tests/security/test_report_tiers.py` proves the serializers cannot *emit* a
field above their tier. This file proves the tiers are reachable only by the
right caller in the first place -- a perfect serializer behind a missing
authorization check protects nothing.

Two doors, deliberately separate routes rather than one route that widens by
role:

* `GET /v1/startups/{startup_id}/audits/{run_id}/report` -- the founder's own.
* `GET /v1/admin/startups/{startup_id}/audits/{run_id}/report` -- SACI, in full.

The properties asserted here are the ones a later edit is most likely to break:
another founder gets `404` and never `403`; an **investor** gets nothing at all
through either door, because their route to a report is a SACI reveal and not an
entitlement; and a report that does not exist yet is `404` rather than a `200`
carrying nulls, which a client would render as a real but empty verdict.
"""

import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import Citation, DataSufficiency
from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError
from app.core.security import AccountStatus, CurrentUser, Role
from app.modules.audit import service as audit
from app.modules.audit.models import AuditRun
from app.modules.audit.reports import admin_report, founder_report
from app.modules.audit.rubric.v1 import Dimension, DimensionScore
from app.modules.audit.runs import AuditStatus
from app.modules.audit.schemas import report_to_storage
from app.modules.audit.synthesis import synthesise
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
    # Admin capabilities require MFA (AUTH.md section 9). Promoting the row
    # without flipping the flag would leave the actor looking enrolled in the
    # ORM and unenrolled in CurrentUser -- or the reverse -- and either way
    # the suite would stop matching the production gate.
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

RATIONALE_SENTINEL = "SENTINEL-rationale-only-the-founder-and-saci"
DETAIL_SENTINEL = "SENTINEL-detail-engineer-facing"


def _stored_report() -> dict:
    report = synthesise(
        rubric_version="v1",
        scores=[
            DimensionScore(
                dimension=dimension,
                score=60,
                rationale="fixture",
                sufficiency=DataSufficiency.SUFFICIENT,
                citations=[Citation(source_id="startup_profile", quote="revenue")],
            )
            for dimension in Dimension
        ],
        data_integrity_score=Decimal(90),
    )
    stored = report_to_storage(report)
    stored["fundability"]["rationale"] = RATIONALE_SENTINEL
    stored["findings"] = [
        {
            "code": "churn_implausibly_low",
            "severity": "likely",
            "fields": ["monthly_churn_percent"],
            "message": "founder-facing message",
            "detail": DETAIL_SENTINEL,
        }
    ]
    return stored


async def _succeeded_run(
    session: AsyncSession, actor: CurrentUser
) -> tuple[uuid.UUID, AuditRun]:
    """A profile with one run that has finished and stored a report."""
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
    run, _ = await audit.request_audit(session, actor, profile.id)
    run.status = AuditStatus.SUCCEEDED
    run.report = _stored_report()
    await session.flush()
    return profile.id, run


class TestTheFoundersOwnDoor:
    async def test_a_founder_reads_their_own_report(
        self, db_session: AsyncSession
    ) -> None:
        _, actor = await _user(db_session)
        startup_id, run = await _succeeded_run(db_session, actor)

        stored = await audit.get_audit_report(db_session, actor, startup_id, run.id)

        assert founder_report(stored).fundability.rationale == RATIONALE_SENTINEL

    async def test_another_founders_report_is_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """`404`, never `403` -- a 403 would confirm the run id is real."""
        _, owner = await _user(db_session)
        startup_id, run = await _succeeded_run(db_session, owner)
        _, intruder = await _user(db_session)

        with pytest.raises(NotFoundError):
            await audit.get_audit_report(db_session, intruder, startup_id, run.id)

    async def test_an_investor_cannot_read_a_report_through_this_door(
        self, db_session: AsyncSession
    ) -> None:
        """The one that matters most.

        An investor's route to report content is the summary serializer through
        discovery, and to a *full* report a SACI reveal at the meeting. Neither
        is an ownership read, so `owned_or_404` must refuse them here exactly as
        it refuses an unrelated founder -- `core.ownership` exempts admins and
        deliberately does not exempt investors.
        """
        _, owner = await _user(db_session)
        startup_id, run = await _succeeded_run(db_session, owner)
        _, investor = await _user(db_session, role=Role.INVESTOR)

        with pytest.raises(NotFoundError):
            await audit.get_audit_report(db_session, investor, startup_id, run.id)

    async def test_pairing_your_own_startup_with_someone_elses_run_is_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """The path's `startup_id` is checked against the row, not trusted.

        Two founders, because a founder may hold only one startup profile --
        `intake.create_profile` raises `ConflictError` on the second, so an
        earlier draft of this test that gave one owner two startups was
        asserting against an impossible arrangement.

        Belt and braces rather than the only wall: ownership alone would also
        refuse this, since the run belongs to the other founder. The check
        matters because the two guards fail differently under a future edit,
        and a caller must never learn from a status code that a run id is real.
        """
        _, mine = await _user(db_session)
        my_startup_id, _ = await _succeeded_run(db_session, mine)
        _, theirs = await _user(db_session)
        _, their_run = await _succeeded_run(db_session, theirs)

        with pytest.raises(NotFoundError):
            await audit.get_audit_report(db_session, mine, my_startup_id, their_run.id)


class TestAReportThatDoesNotExistYet:
    @pytest.mark.parametrize(
        "status",
        [AuditStatus.QUEUED, AuditStatus.RUNNING, AuditStatus.FAILED],
    )
    async def test_a_run_that_has_not_succeeded_is_not_found(
        self, db_session: AsyncSession, status: AuditStatus
    ) -> None:
        """`404`, not a `200` carrying nulls.

        An empty success would have a client rendering a blank verdict as a
        real one -- the same false-verdict shape `CLAUDE.md` section 5 forbids,
        arriving through the transport rather than through the model.
        """
        _, actor = await _user(db_session)
        startup_id, run = await _succeeded_run(db_session, actor)
        run.status = status
        run.report = None
        await db_session.flush()

        with pytest.raises(NotFoundError):
            await audit.get_audit_report(db_session, actor, startup_id, run.id)

    async def test_a_succeeded_run_with_no_report_is_still_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Belt and braces: status and payload are checked independently.

        A run marked `succeeded` whose report never persisted is a bug, but the
        endpoint must not turn it into a `500` or a null-filled `200`.
        """
        _, actor = await _user(db_session)
        startup_id, run = await _succeeded_run(db_session, actor)
        run.report = None
        await db_session.flush()

        with pytest.raises(NotFoundError):
            await audit.get_audit_report(db_session, actor, startup_id, run.id)


class TestTheAdminDoor:
    async def test_saci_reads_any_report_in_full(
        self, db_session: AsyncSession
    ) -> None:
        _, owner = await _user(db_session)
        startup_id, run = await _succeeded_run(db_session, owner)
        _, admin = await _user(db_session, role=Role.ADMIN)

        stored = await audit.get_audit_report(db_session, admin, startup_id, run.id)

        assert admin_report(stored).findings[0].detail == DETAIL_SENTINEL

    async def test_the_admin_serializer_is_the_only_one_carrying_detail(
        self, db_session: AsyncSession
    ) -> None:
        """Same stored document, two tiers, and the wider one is admin-only."""
        _, owner = await _user(db_session)
        startup_id, run = await _succeeded_run(db_session, owner)

        stored = await audit.get_audit_report(db_session, owner, startup_id, run.id)

        assert not hasattr(founder_report(stored).findings[0], "detail")


class TestTheRoleGuardOnTheAdminRoute:
    """The admin route's guard is in the router, so it is asserted directly.

    `get_audit_report` deliberately does not know which door it was called
    through -- one service method serves both, and the tier is the router's
    serializer choice. That puts the role check in `read_audit_report_as_admin`,
    and a check that lives in a router is a check a test has to reach for on
    purpose.
    """

    async def test_a_founder_is_refused_the_admin_route(
        self, db_session: AsyncSession
    ) -> None:
        from app.modules.audit.router import read_audit_report_as_admin

        _, actor = await _user(db_session)
        startup_id, run = await _succeeded_run(db_session, actor)

        with pytest.raises(ForbiddenError):
            await read_audit_report_as_admin(startup_id, run.id, actor, db_session)

    async def test_an_investor_is_refused_the_admin_route(
        self, db_session: AsyncSession
    ) -> None:
        from app.modules.audit.router import read_audit_report_as_admin

        _, owner = await _user(db_session)
        startup_id, run = await _succeeded_run(db_session, owner)
        _, investor = await _user(db_session, role=Role.INVESTOR)

        with pytest.raises(ForbiddenError):
            await read_audit_report_as_admin(startup_id, run.id, investor, db_session)
