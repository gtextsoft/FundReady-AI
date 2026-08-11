"""Investor discovery: who is listed, and what a card may carry (T4.3).

**This is the first endpoint in the platform where one user reads about
another.** Everywhere else a caller reads their own rows and `owned_or_404`
settles it. Here an investor reads across tenants by design, so the failure mode
is not "IDOR" but "we published everybody" -- a list endpoint over other
people's confidential businesses, one missing filter away from disaster.

Three properties, in descending order of how much they would cost to get wrong:

* **Only published startups appear.** Running an audit is not consent. A founder
  who never opted in must not be listed, must not be readable by id, and must
  not be distinguishable from a startup that does not exist.
* **A card carries summary tier only.** No submitted figures, no rationale, no
  findings, no action plan, no contact detail.
* **Founders cannot browse.** Discovery is for investors and SACI.
"""

import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import Citation, DataSufficiency
from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError
from app.core.security import AccountStatus, CurrentUser, KycStatus, Role
from app.modules.audit import service as audit
from app.modules.audit.rubric.v1 import Dimension, DimensionScore
from app.modules.audit.runs import AuditStatus
from app.modules.audit.schemas import report_to_storage
from app.modules.audit.synthesis import synthesise
from app.modules.identity import service as identity
from app.modules.identity.models import User
from app.modules.intake import service as intake
from app.modules.intake.fields import Stage
from app.modules.investor import service as investor
from app.modules.investor.schemas import DiscoveryFilters
from tests.conftest import requires_database

pytestmark = [pytest.mark.security, pytest.mark.integration, requires_database]

PASSWORD = "correct-horse-battery-staple"

RATIONALE_SENTINEL = "SENTINEL-rationale-founder-and-saci-only"
FINDING_SENTINEL = "SENTINEL-finding-their-numbers-disagree"
ACTION_SENTINEL = "SENTINEL-action-everything-still-wrong"
REVENUE_SENTINEL = 987_654_321


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
        kyc_status=user.kyc_status,
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
    if role is Role.ADMIN:
        user.mfa_enabled = True
    if role is Role.INVESTOR:
        # Discovery is KYC-gated; fixtures that browse need a verified actor.
        user.kyc_status = KycStatus.VERIFIED
    await session.flush()
    return user, _actor(user)


def _stored() -> dict:
    report = synthesise(
        rubric_version="v1",
        scores=[
            DimensionScore(
                dimension=dimension,
                score=61,
                rationale="fixture",
                sufficiency=DataSufficiency.SUFFICIENT,
                citations=[Citation(source_id="startup_profile", quote="revenue")],
                unmet_criteria=[ACTION_SENTINEL] if dimension is Dimension.TEAM else [],
            )
            for dimension in Dimension
        ],
        data_integrity_score=Decimal(88),
    )
    stored = report_to_storage(report)
    stored["fundability"]["rationale"] = RATIONALE_SENTINEL
    stored["saleability"]["rationale"] = RATIONALE_SENTINEL
    stored["findings"] = [
        {
            "code": "churn_implausibly_low",
            "severity": "likely",
            "fields": ["monthly_churn_percent"],
            "message": FINDING_SENTINEL,
            "detail": "engineer facing",
        }
    ]
    return stored


async def _startup(
    session: AsyncSession,
    owner: CurrentUser,
    *,
    published: bool,
    audited: bool = True,
    sector: str = "fintech",
    country: str = "NG",
) -> uuid.UUID:
    profile = await intake.create_profile(
        session,
        owner,
        {
            "name": "Kanmi Pay",
            "sector": sector,
            "stage": Stage.SEED,
            "country": country,
            "currency": "NGN",
            "fields": {
                "description": {"value": "Payments for pharmacies."},
                "business_model": {"value": "Per transaction."},
                "team_size": {"value": 10},
                "monthly_revenue_minor": {"value": REVENUE_SENTINEL},
                "monthly_costs_minor": {"value": 4_000_000},
                "cash_on_hand_minor": {"value": 20_000_000},
            },
        },
    )
    if audited:
        run, _ = await audit.request_audit(session, owner, profile.id)
        run.status = AuditStatus.SUCCEEDED
        run.report = _stored()
    if published:
        await intake.set_discoverability(session, owner, profile.id, visible=True)
    await session.flush()
    return profile.id


class TestOnlyPublishedStartupsAreVisible:
    async def test_an_unpublished_startup_is_not_listed(
        self, db_session: AsyncSession
    ) -> None:
        """Running an audit is not consent to be shown to investors."""
        _, owner = await _user(db_session)
        startup_id = await _startup(db_session, owner, published=False)
        _, viewer = await _user(db_session, role=Role.INVESTOR)

        page = await investor.discover(
            db_session, viewer, DiscoveryFilters(), limit=100, offset=0
        )

        assert startup_id not in {card.startup_id for card in page.items}

    async def test_an_unpublished_startup_is_not_readable_by_id(
        self, db_session: AsyncSession
    ) -> None:
        """`404`, identical to a startup that does not exist.

        A distinguishable answer would turn discovery into an oracle for which
        startup ids are real -- the same reason ownership denials are `404`.
        """
        _, owner = await _user(db_session)
        startup_id = await _startup(db_session, owner, published=False)
        _, viewer = await _user(db_session, role=Role.INVESTOR)

        with pytest.raises(NotFoundError):
            await investor.visible_startup(db_session, viewer, startup_id)

        with pytest.raises(NotFoundError):
            await investor.visible_startup(db_session, viewer, uuid.uuid4())

    async def test_publishing_without_an_audit_lists_nothing(
        self, db_session: AsyncSession
    ) -> None:
        """Consent is not eligibility.

        `set_discoverability` accepts the opt-in with no audit check, on
        purpose -- checking there would mean `intake` importing `audit`, which
        already imports `intake`. The guarantee lives in the discovery join
        instead, and this is the test that says the join is the real gate.
        """
        _, owner = await _user(db_session)
        startup_id = await _startup(db_session, owner, published=True, audited=False)
        _, viewer = await _user(db_session, role=Role.INVESTOR)

        page = await investor.discover(
            db_session, viewer, DiscoveryFilters(), limit=100, offset=0
        )

        assert startup_id not in {card.startup_id for card in page.items}

    async def test_unpublishing_removes_it_again(
        self, db_session: AsyncSession
    ) -> None:
        _, owner = await _user(db_session)
        startup_id = await _startup(db_session, owner, published=True)
        _, viewer = await _user(db_session, role=Role.INVESTOR)

        await intake.set_discoverability(db_session, owner, startup_id, visible=False)
        await db_session.flush()

        with pytest.raises(NotFoundError):
            await investor.visible_startup(db_session, viewer, startup_id)

    async def test_a_published_audited_startup_is_listed(
        self, db_session: AsyncSession
    ) -> None:
        """The wall has to let the product through, or it is only a wall."""
        _, owner = await _user(db_session)
        startup_id = await _startup(db_session, owner, published=True)
        _, viewer = await _user(db_session, role=Role.INVESTOR)

        page = await investor.discover(
            db_session, viewer, DiscoveryFilters(), limit=100, offset=0
        )

        assert startup_id in {card.startup_id for card in page.items}
        assert page.total >= 1


class TestACardCarriesSummaryTierOnly:
    async def test_no_report_internals_reach_the_card(
        self, db_session: AsyncSession
    ) -> None:
        """Searches the whole serialized card, not a list of keys."""
        _, owner = await _user(db_session)
        startup_id = await _startup(db_session, owner, published=True)
        _, viewer = await _user(db_session, role=Role.INVESTOR)

        card = await investor.visible_startup(db_session, viewer, startup_id)
        payload = card.model_dump_json()

        for sentinel in (RATIONALE_SENTINEL, FINDING_SENTINEL, ACTION_SENTINEL):
            assert sentinel not in payload, f"card leaked {sentinel}"

    async def test_no_submitted_figures_reach_the_card(
        self, db_session: AsyncSession
    ) -> None:
        """The founder's own numbers are the thing SACI brokers access to.

        An investor gets the verdict, which is what the audit is *for*. The
        revenue behind it comes with the introduction.
        """
        _, owner = await _user(db_session)
        startup_id = await _startup(db_session, owner, published=True)
        _, viewer = await _user(db_session, role=Role.INVESTOR)

        card = await investor.visible_startup(db_session, viewer, startup_id)

        assert str(REVENUE_SENTINEL) not in card.model_dump_json()
        assert not hasattr(card, "fields")

    async def test_the_verdicts_do_come_through(self, db_session: AsyncSession) -> None:
        _, owner = await _user(db_session)
        startup_id = await _startup(db_session, owner, published=True)
        _, viewer = await _user(db_session, role=Role.INVESTOR)

        card = await investor.visible_startup(db_session, viewer, startup_id)

        assert card.fundability.level
        assert card.saleability.level
        assert card.audit_run_id is not None


class TestWhoMayBrowse:
    async def test_a_founder_cannot_browse_other_startups(
        self, db_session: AsyncSession
    ) -> None:
        """Not a feature anyone asked for, and exactly the kind of access that
        gets granted by accident when an endpoint checks only for a login."""
        _, owner = await _user(db_session)
        await _startup(db_session, owner, published=True)
        _, nosy = await _user(db_session)

        with pytest.raises(ForbiddenError):
            await investor.discover(
                db_session, nosy, DiscoveryFilters(), limit=10, offset=0
            )

    async def test_saci_may_browse(self, db_session: AsyncSession) -> None:
        """Admins see what an investor sees, for when a founder disputes it."""
        _, owner = await _user(db_session)
        startup_id = await _startup(db_session, owner, published=True)
        _, admin = await _user(db_session, role=Role.ADMIN)

        card = await investor.visible_startup(db_session, admin, startup_id)

        assert card.startup_id == startup_id


class TestFilters:
    async def test_sector_matches_case_insensitively(
        self, db_session: AsyncSession
    ) -> None:
        """Sector is free text (D11), so an exact match would silently miss."""
        _, owner = await _user(db_session)
        startup_id = await _startup(db_session, owner, published=True, sector="Fintech")
        _, viewer = await _user(db_session, role=Role.INVESTOR)

        page = await investor.discover(
            db_session, viewer, DiscoveryFilters(sector="fintech"), limit=100, offset=0
        )

        assert startup_id in {card.startup_id for card in page.items}

    async def test_a_non_matching_filter_excludes_it(
        self, db_session: AsyncSession
    ) -> None:
        _, owner = await _user(db_session)
        startup_id = await _startup(db_session, owner, published=True, country="NG")
        _, viewer = await _user(db_session, role=Role.INVESTOR)

        page = await investor.discover(
            db_session, viewer, DiscoveryFilters(country="GB"), limit=100, offset=0
        )

        assert startup_id not in {card.startup_id for card in page.items}
