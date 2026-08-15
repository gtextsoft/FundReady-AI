"""Thesis gate, watchlist isolation, verification ownership, inbox isolation."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError
from app.core.security import AccountStatus, CurrentUser, Role
from app.modules.identity import service as identity
from app.modules.identity.models import User
from app.modules.intake import service as intake
from app.modules.intake.models import CompanyVerificationStatus
from app.modules.investor import service as investor
from app.modules.investor.models import ThesisReviewStatus
from app.modules.investor.repository import InvestorProfileRepository
from app.modules.investor.schemas import InvestorProfileUpdate
from app.modules.notifications import inbox
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


def _actor(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        role=user.role,
        status=AccountStatus.ACTIVE,
        email_verified=True,
        mfa_enabled=user.mfa_enabled,
        kyc_status=user.kyc_status,
    )


async def _user(session: AsyncSession, role: Role) -> tuple[User, CurrentUser]:
    user = await identity.register_user(
        session,
        email=f"user-{uuid.uuid4().hex}@example.test",
        password=PASSWORD,
        role=Role.FOUNDER if role is Role.FOUNDER else role,
        first_name="Ada",
        last_name="Tester",
    )
    assert user is not None
    user.role = role
    user.status = AccountStatus.ACTIVE
    if role is Role.ADMIN:
        user.mfa_enabled = True
    await session.flush()
    return user, _actor(user)


class TestThesisGate:
    async def test_put_sets_in_review(self, db_session: AsyncSession) -> None:
        _, actor = await _user(db_session, Role.INVESTOR)
        profile = await investor.update_profile(
            db_session,
            actor,
            InvestorProfileUpdate(firm="Sahel", thesis_sectors=["fintech"]),
        )
        assert profile.review_status is ThesisReviewStatus.IN_REVIEW

    async def test_unaccepted_investor_cannot_watch(
        self, db_session: AsyncSession
    ) -> None:
        _, founder = await _user(db_session, Role.FOUNDER)
        profile = await intake.create_profile(db_session, founder, {"name": "Kanmi"})
        _, investor_actor = await _user(db_session, Role.INVESTOR)
        with pytest.raises(ForbiddenError):
            await investor.toggle_watch(db_session, investor_actor, profile.id)


class TestWatchlistIsolation:
    async def test_watchlist_is_per_investor(self, db_session: AsyncSession) -> None:
        _, a = await _user(db_session, Role.INVESTOR)
        _, b = await _user(db_session, Role.INVESTOR)
        await inbox.notify(
            db_session, a.id, kind="thesis_review", title="A", body="A"
        )
        mine = await inbox.list_for_user(db_session, a, limit=20, offset=0)
        theirs = await inbox.list_for_user(db_session, b, limit=20, offset=0)
        assert mine.total == 1
        assert theirs.total == 0


class TestCompanyVerification:
    async def test_another_founder_cannot_submit(
        self, db_session: AsyncSession
    ) -> None:
        _, owner = await _user(db_session, Role.FOUNDER)
        profile = await intake.create_profile(db_session, owner, {"name": "Kanmi"})
        _, other = await _user(db_session, Role.FOUNDER)
        with pytest.raises(NotFoundError):
            await intake.submit_company_verification(db_session, other, profile.id)

    async def test_owner_moves_to_in_review(self, db_session: AsyncSession) -> None:
        _, owner = await _user(db_session, Role.FOUNDER)
        profile = await intake.create_profile(db_session, owner, {"name": "Kanmi"})
        updated = await intake.submit_company_verification(
            db_session, owner, profile.id
        )
        assert updated.company_verification_status is CompanyVerificationStatus.IN_REVIEW


class TestNotificationsIsolation:
    async def test_mark_read_ignores_another_users_ids(
        self, db_session: AsyncSession
    ) -> None:
        _, a = await _user(db_session, Role.FOUNDER)
        _, b = await _user(db_session, Role.FOUNDER)
        await inbox.notify(
            db_session, a.id, kind="audit_ready", title="Ready", body="Open it."
        )
        page = await inbox.list_for_user(db_session, a, limit=20, offset=0)
        foreign_id = page.items[0].id
        await inbox.mark_read(db_session, b, [foreign_id])
        again = await inbox.list_for_user(db_session, a, limit=20, offset=0)
        assert again.items[0].read_at is None


class TestAcceptedThesisHelper:
    async def test_accepted_row_exists_after_admin_decide(
        self, db_session: AsyncSession
    ) -> None:
        user, actor = await _user(db_session, Role.INVESTOR)
        await investor.update_profile(
            db_session, actor, InvestorProfileUpdate(firm="Sahel")
        )
        _, admin = await _user(db_session, Role.ADMIN)
        card = await investor.decide_thesis(db_session, admin, user.id, accept=True)
        assert card.review_status is ThesisReviewStatus.ACCEPTED
        row = await InvestorProfileRepository(db_session).get(user.id)
        assert row is not None
        assert row.review_status is ThesisReviewStatus.ACCEPTED


class TestMyMeetings:
    @pytest.fixture(autouse=True)
    def no_redis(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.modules.audit import service as audit

        monkeypatch.setattr(audit, "enqueue_audit", lambda _run_id: None)

    async def test_founder_sees_scheduled_not_proposed(
        self, db_session: AsyncSession
    ) -> None:
        from datetime import UTC, datetime, timedelta

        from app.ai.schemas import Citation, DataSufficiency
        from app.modules.audit import service as audit
        from app.modules.audit.rubric.v1 import Dimension, DimensionScore
        from app.modules.audit.runs import AuditStatus
        from app.modules.audit.schemas import report_to_storage
        from app.modules.audit.synthesis import synthesise
        from app.modules.brokerage import service as brokerage
        from app.modules.intake.fields import Stage

        _founder_user, founder = await _user(db_session, Role.FOUNDER)
        _other_user, other = await _user(db_session, Role.FOUNDER)
        inv_user, inv = await _user(db_session, Role.INVESTOR)
        _, admin = await _user(db_session, Role.ADMIN)

        await investor.update_profile(
            db_session, inv, InvestorProfileUpdate(firm="Sahel")
        )
        await investor.decide_thesis(db_session, admin, inv_user.id, accept=True)

        profile = await intake.create_profile(
            db_session,
            founder,
            {
                "name": "Kanmi Pay",
                "sector": "fintech",
                "stage": Stage.SEED,
                "country": "NG",
                "currency": "NGN",
                "fields": {
                    "description": {"value": "Payments."},
                    "business_model": {"value": "Fee."},
                    "team_size": {"value": 8},
                    "monthly_revenue_minor": {"value": 5_000_000},
                    "monthly_costs_minor": {"value": 4_000_000},
                    "cash_on_hand_minor": {"value": 20_000_000},
                },
            },
        )
        run, _ = await audit.request_audit(db_session, founder, profile.id)
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
            data_integrity_score=__import__("decimal").Decimal(90),
        )
        run.status = AuditStatus.SUCCEEDED
        run.report = report_to_storage(report)
        await intake.set_discoverability(db_session, founder, profile.id, visible=True)
        await db_session.flush()

        interest = await brokerage.express_interest(db_session, inv, profile.id)
        await brokerage.decide_interest(db_session, admin, interest.id, approve=True)

        when = datetime.now(UTC) + timedelta(days=3)
        proposed = await brokerage.propose_meeting(
            db_session,
            inv,
            interest.id,
            scheduled_at=when,
            duration_minutes=45,
            message="After 10 WAT",
        )
        assert proposed.status.value == "proposed"

        founder_rows = await brokerage.list_my_meetings(db_session, founder)
        assert founder_rows == []
        other_rows = await brokerage.list_my_meetings(db_session, other)
        assert other_rows == []
        inv_rows = await brokerage.list_my_meetings(db_session, inv)
        assert [row.id for row in inv_rows] == [proposed.id]

        confirmed = await brokerage.confirm_meeting(
            db_session,
            admin,
            interest.id,
            proposed.id,
            scheduled_at=None,
            duration_minutes=None,
            location="https://meet.saci.example/intro",
            notes=None,
        )
        assert confirmed.status.value == "scheduled"

        founder_rows = await brokerage.list_my_meetings(db_session, founder)
        assert [row.id for row in founder_rows] == [confirmed.id]
        other_rows = await brokerage.list_my_meetings(db_session, other)
        assert other_rows == []
