"""The SACI reveal: the one sanctioned way a full report leaves its owner (T4.6).

Every other report-tier control in this codebase is a serializer declining to
emit a field. This is the deliberate exception `CLAUDE.md` section 4 permits,
which makes it the highest-value thing in the suite to get wrong.

The property that matters most is **approval is not disclosure**. An investor
whose interest SACI approved still sees nothing new: they get the full report
only when an admin separately reveals it. If those two ever collapse into one
action, every approved interest becomes a full disclosure and nobody finds out
until a founder asks how an investor knew their numbers.
"""

import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import Citation, DataSufficiency
from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.security import AccountStatus, CurrentUser, Role
from app.modules.audit import service as audit
from app.modules.audit.rubric.v1 import Dimension, DimensionScore
from app.modules.audit.runs import AuditStatus
from app.modules.audit.schemas import report_to_storage
from app.modules.audit.synthesis import synthesise
from app.modules.brokerage import service as brokerage
from app.modules.identity import service as identity
from app.modules.identity.models import User
from app.modules.intake import service as intake
from app.modules.intake.fields import Stage
from tests.conftest import requires_database

pytestmark = [pytest.mark.security, pytest.mark.integration, requires_database]

PASSWORD = "correct-horse-battery-staple"
RATIONALE_SENTINEL = "SENTINEL-rationale-revealed-only-by-saci"


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


async def _user(session: AsyncSession, role: Role = Role.FOUNDER) -> CurrentUser:
    user: User | None = await identity.register_user(
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
    if role is Role.INVESTOR:
        from app.modules.investor.models import ThesisReviewStatus
        from app.modules.investor.repository import InvestorProfileRepository

        row = await InvestorProfileRepository(session).get_or_create(user.id)
        row.review_status = ThesisReviewStatus.ACCEPTED
        await session.flush()
    return CurrentUser(
        id=user.id,
        role=role,
        status=AccountStatus.ACTIVE,
        email_verified=True,
        mfa_enabled=(role is Role.ADMIN),
    )


async def _published_startup(session: AsyncSession, owner: CurrentUser) -> uuid.UUID:
    profile = await intake.create_profile(
        session,
        owner,
        {
            "name": "Kanmi Pay",
            "sector": "fintech",
            "stage": Stage.SEED,
            "country": "NG",
            "currency": "NGN",
            "fields": {
                "description": {"value": "Payments for pharmacies."},
                "business_model": {"value": "Per transaction."},
                "team_size": {"value": 10},
                "monthly_revenue_minor": {"value": 5_000_000},
                "monthly_costs_minor": {"value": 4_000_000},
                "cash_on_hand_minor": {"value": 20_000_000},
            },
        },
    )
    run, _ = await audit.request_audit(session, owner, profile.id)
    report = synthesise(
        rubric_version="v1",
        scores=[
            DimensionScore(
                dimension=d,
                score=60,
                rationale="fixture",
                sufficiency=DataSufficiency.SUFFICIENT,
                citations=[Citation(source_id="startup_profile", quote="revenue")],
            )
            for d in Dimension
        ],
        data_integrity_score=Decimal(90),
    )
    stored = report_to_storage(report)
    stored["fundability"]["rationale"] = RATIONALE_SENTINEL
    run.status = AuditStatus.SUCCEEDED
    run.report = stored
    await intake.set_discoverability(session, owner, profile.id, visible=True)
    await session.flush()
    return profile.id


class TestApprovalIsNotDisclosure:
    """The single most important behaviour in this file."""

    async def test_an_approved_interest_alone_reveals_nothing(
        self, db_session: AsyncSession
    ) -> None:
        """SACI agreeing to broker is not SACI handing over the report."""
        owner = await _user(db_session)
        startup_id = await _published_startup(db_session, owner)
        inv = await _user(db_session, Role.INVESTOR)
        admin = await _user(db_session, Role.ADMIN)

        interest = await brokerage.express_interest(db_session, inv, startup_id)
        await brokerage.decide_interest(db_session, admin, interest.id, approve=True)
        run_id = (await audit.list_audit_runs(db_session, owner, startup_id))[0].id

        with pytest.raises(NotFoundError):
            await brokerage.read_revealed_report(db_session, inv, interest.id, run_id)

    async def test_after_a_reveal_the_investor_can_read_it(
        self, db_session: AsyncSession
    ) -> None:
        owner = await _user(db_session)
        startup_id = await _published_startup(db_session, owner)
        inv = await _user(db_session, Role.INVESTOR)
        admin = await _user(db_session, Role.ADMIN)

        interest = await brokerage.express_interest(db_session, inv, startup_id)
        await brokerage.decide_interest(db_session, admin, interest.id, approve=True)
        reveal = await brokerage.reveal_report(db_session, admin, interest.id)

        report = await brokerage.read_revealed_report(
            db_session, inv, interest.id, reveal.audit_run_id
        )

        assert report.fundability.rationale == RATIONALE_SENTINEL


class TestWhoMayReveal:
    async def test_an_investor_cannot_reveal_to_themselves(
        self, db_session: AsyncSession
    ) -> None:
        """Otherwise the brokerage is a formality the investor performs alone."""
        owner = await _user(db_session)
        startup_id = await _published_startup(db_session, owner)
        inv = await _user(db_session, Role.INVESTOR)
        admin = await _user(db_session, Role.ADMIN)

        interest = await brokerage.express_interest(db_session, inv, startup_id)
        await brokerage.decide_interest(db_session, admin, interest.id, approve=True)

        with pytest.raises(ForbiddenError):
            await brokerage.reveal_report(db_session, inv, interest.id)

    async def test_a_founder_cannot_reveal(self, db_session: AsyncSession) -> None:
        owner = await _user(db_session)
        startup_id = await _published_startup(db_session, owner)
        inv = await _user(db_session, Role.INVESTOR)
        admin = await _user(db_session, Role.ADMIN)

        interest = await brokerage.express_interest(db_session, inv, startup_id)
        await brokerage.decide_interest(db_session, admin, interest.id, approve=True)

        with pytest.raises(ForbiddenError):
            await brokerage.reveal_report(db_session, owner, interest.id)

    async def test_revealing_a_pending_interest_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        """Revealing without approving would make approval decorative."""
        owner = await _user(db_session)
        startup_id = await _published_startup(db_session, owner)
        inv = await _user(db_session, Role.INVESTOR)
        admin = await _user(db_session, Role.ADMIN)

        interest = await brokerage.express_interest(db_session, inv, startup_id)

        with pytest.raises(ConflictError):
            await brokerage.reveal_report(db_session, admin, interest.id)

    async def test_revealing_a_declined_interest_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        owner = await _user(db_session)
        startup_id = await _published_startup(db_session, owner)
        inv = await _user(db_session, Role.INVESTOR)
        admin = await _user(db_session, Role.ADMIN)

        interest = await brokerage.express_interest(db_session, inv, startup_id)
        await brokerage.decide_interest(db_session, admin, interest.id, approve=False)

        with pytest.raises(ConflictError):
            await brokerage.reveal_report(db_session, admin, interest.id)


class TestOneRevealReachesOneInvestor:
    async def test_another_investor_cannot_read_the_revealed_report(
        self, db_session: AsyncSession
    ) -> None:
        """A reveal is to a *person*, not to a class of user.

        Without this, one approved investor anywhere on the platform would open
        the report to every investor who could guess an interest id.
        """
        owner = await _user(db_session)
        startup_id = await _published_startup(db_session, owner)
        inv = await _user(db_session, Role.INVESTOR)
        other = await _user(db_session, Role.INVESTOR)
        admin = await _user(db_session, Role.ADMIN)

        interest = await brokerage.express_interest(db_session, inv, startup_id)
        await brokerage.decide_interest(db_session, admin, interest.id, approve=True)
        reveal = await brokerage.reveal_report(db_session, admin, interest.id)

        with pytest.raises(NotFoundError):
            await brokerage.read_revealed_report(
                db_session, other, interest.id, reveal.audit_run_id
            )

    async def test_revealing_twice_is_one_disclosure(
        self, db_session: AsyncSession
    ) -> None:
        """Idempotent, so a retried request does not imply a second disclosure."""
        owner = await _user(db_session)
        startup_id = await _published_startup(db_session, owner)
        inv = await _user(db_session, Role.INVESTOR)
        admin = await _user(db_session, Role.ADMIN)

        interest = await brokerage.express_interest(db_session, inv, startup_id)
        await brokerage.decide_interest(db_session, admin, interest.id, approve=True)

        first = await brokerage.reveal_report(db_session, admin, interest.id)
        second = await brokerage.reveal_report(db_session, admin, interest.id)

        assert first.audit_run_id == second.audit_run_id
        assert first.revealed_at == second.revealed_at


class TestExpressingInterest:
    async def test_interest_in_an_unpublished_startup_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        """The discovery filter guards the write as well as the browse."""
        owner = await _user(db_session)
        startup_id = await _published_startup(db_session, owner)
        await intake.set_discoverability(db_session, owner, startup_id, visible=False)
        await db_session.flush()
        inv = await _user(db_session, Role.INVESTOR)

        with pytest.raises(NotFoundError):
            await brokerage.express_interest(db_session, inv, startup_id)

    async def test_a_founder_cannot_express_interest(
        self, db_session: AsyncSession
    ) -> None:
        owner = await _user(db_session)
        startup_id = await _published_startup(db_session, owner)
        nosy = await _user(db_session)

        with pytest.raises(ForbiddenError):
            await brokerage.express_interest(db_session, nosy, startup_id)

    async def test_expressing_twice_returns_the_original(
        self, db_session: AsyncSession
    ) -> None:
        owner = await _user(db_session)
        startup_id = await _published_startup(db_session, owner)
        inv = await _user(db_session, Role.INVESTOR)

        first = await brokerage.express_interest(db_session, inv, startup_id)
        second = await brokerage.express_interest(db_session, inv, startup_id)

        assert first.id == second.id
