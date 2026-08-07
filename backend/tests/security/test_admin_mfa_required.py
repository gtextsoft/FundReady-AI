"""Admin capabilities require MFA -- including the ones that used to skip it.

`AUTH.md` section 9 and T1.2c say no admin capability is reachable without a
second factor. `require_role(Role.ADMIN)` enforces that at the HTTP boundary,
but four capabilities -- report reveal, the admin-tier report, benchmark CRUD,
and readiness-task reopen -- previously took `CurrentUserDep` and compared
`actor.role` inline, so an unenrolled admin holding a valid token reached them
all. These tests are what make that hole stay closed.

Two layers, both asserted:

* **Service** -- `assert_admin` refuses an unenrolled admin at the call site.
* **HTTP** -- `CurrentAdmin` refuses the same token before the handler runs.

Each refusal was proven able to fail by reverting one call site at a time
(service `_require_admin` role-only, or a route left on `CurrentUserDep`); a
green suite that never saw the old behaviour is how the hole survived.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import Citation, DataSufficiency
from app.core.config import get_settings
from app.core.db import get_session
from app.core.deps import CurrentAdmin
from app.core.errors import ErrorCode, ForbiddenError, register_exception_handlers
from app.core.logging import RequestContextMiddleware
from app.core.security import (
    AccountStatus,
    CurrentUser,
    Role,
    assert_admin,
    create_access_token,
    set_user_loader,
)
from app.modules.audit import service as audit
from app.modules.audit.benchmarks import BenchmarkMetric, Stage
from app.modules.audit.router import read_audit_report_as_admin
from app.modules.audit.rubric.v1 import Dimension, DimensionScore
from app.modules.audit.runs import AuditStatus
from app.modules.audit.schemas import report_to_storage
from app.modules.audit.synthesis import synthesise
from app.modules.brokerage import service as brokerage
from app.modules.identity import service as identity
from app.modules.identity.models import User
from app.modules.intake import service as intake
from app.modules.readiness import service as readiness
from app.modules.readiness.generation import Requirement, TaskStatus
from app.modules.readiness.models import ReadinessTask
from tests.conftest import requires_database

pytestmark = [pytest.mark.security]

PASSWORD = "correct-horse-battery-staple"
MFA_MESSAGE = "Admin accounts must enrol in two-factor authentication first."
SIGNING_KEY = "test-signing-key-at-least-32-characters-long"


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("JWT_SECRET_KEY", SIGNING_KEY)
    monkeypatch.setenv("ARGON2_MEMORY_COST_KIB", "8192")
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _admin(*, mfa_enabled: bool) -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        role=Role.ADMIN,
        status=AccountStatus.ACTIVE,
        email_verified=True,
        mfa_enabled=mfa_enabled,
    )


# ---------------------------------------------------------------------------
# assert_admin itself -- no database, no FastAPI
# ---------------------------------------------------------------------------


class TestAssertAdmin:
    def test_an_unenrolled_admin_is_refused(self) -> None:
        with pytest.raises(ForbiddenError, match=MFA_MESSAGE):
            assert_admin(_admin(mfa_enabled=False))

    def test_an_enrolled_admin_passes(self) -> None:
        assert_admin(_admin(mfa_enabled=True))

    def test_a_founder_is_refused(self) -> None:
        founder = CurrentUser(
            id=uuid.uuid4(),
            role=Role.FOUNDER,
            status=AccountStatus.ACTIVE,
            email_verified=True,
        )
        with pytest.raises(ForbiddenError):
            assert_admin(founder)

    def test_a_custom_role_message_is_honoured(self) -> None:
        founder = CurrentUser(
            id=uuid.uuid4(),
            role=Role.FOUNDER,
            status=AccountStatus.ACTIVE,
            email_verified=True,
        )
        with pytest.raises(ForbiddenError, match="Only a SACI admin"):
            assert_admin(founder, message="Only a SACI admin can reopen a task.")

    def test_mfa_refusal_ignores_the_custom_role_message(self) -> None:
        """Otherwise an unenrolled admin would see 'role wrong' and enrol nothing."""
        with pytest.raises(ForbiddenError, match=MFA_MESSAGE):
            assert_admin(
                _admin(mfa_enabled=False),
                message="Only a SACI admin can reopen a task.",
            )


# ---------------------------------------------------------------------------
# HTTP boundary -- CurrentAdmin, the synthetic-route pattern
# ---------------------------------------------------------------------------


class TestCurrentAdminOnSyntheticRoutes:
    """Same shape as `test_auth_dependencies.TestAdminSecondFactor`, restated
    here so a future delete of one file does not drop the other.
    """

    @pytest.fixture
    def users(self) -> dict[uuid.UUID, CurrentUser]:
        return {}

    @pytest.fixture(autouse=True)
    def loader(self, users: dict[uuid.UUID, CurrentUser]) -> Iterator[None]:
        async def load(user_id: uuid.UUID) -> CurrentUser | None:
            return users.get(user_id)

        set_user_loader(load)
        yield
        set_user_loader(None)

    @pytest.fixture
    def client(self) -> Iterator[TestClient]:
        app = FastAPI()
        app.add_middleware(RequestContextMiddleware)
        register_exception_handlers(app)

        @app.get("/admin-capability")
        async def admin_capability(_user: CurrentAdmin) -> dict[str, str]:
            return {"ok": "true"}

        with TestClient(app) as test_client:
            yield test_client

    def test_unenrolled_admin_token_is_403(
        self, client: TestClient, users: dict[uuid.UUID, CurrentUser]
    ) -> None:
        admin = _admin(mfa_enabled=False)
        users[admin.id] = admin
        token = create_access_token(admin.id, admin.role, settings=get_settings())

        response = client.get(
            "/admin-capability", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == ErrorCode.FORBIDDEN
        assert MFA_MESSAGE in response.json()["error"]["message"]

    def test_enrolled_admin_token_is_200(
        self, client: TestClient, users: dict[uuid.UUID, CurrentUser]
    ) -> None:
        admin = _admin(mfa_enabled=True)
        users[admin.id] = admin
        token = create_access_token(admin.id, admin.role, settings=get_settings())

        response = client.get(
            "/admin-capability", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Service layer -- the four capabilities that used to skip MFA
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit, "enqueue_audit", lambda _run_id: None)


async def _register_admin(
    session: AsyncSession, *, mfa_enabled: bool
) -> tuple[User, CurrentUser]:
    user = await identity.register_user(
        session,
        email=f"admin-{uuid.uuid4().hex}@example.test",
        password=PASSWORD,
        role=Role.FOUNDER,
        first_name="Ada",
        last_name="Admin",
    )
    assert user is not None
    user.role = Role.ADMIN
    user.status = AccountStatus.ACTIVE
    user.email_verified_at = datetime.now(UTC)
    user.mfa_enabled = mfa_enabled
    await session.flush()
    return user, CurrentUser(
        id=user.id,
        role=Role.ADMIN,
        status=AccountStatus.ACTIVE,
        email_verified=True,
        mfa_enabled=mfa_enabled,
    )


def _band() -> dict[str, object]:
    return {
        "sector": "logistics",
        "stage": Stage.SEED,
        "metric": BenchmarkMetric.GROSS_MARGIN_PERCENT,
        "region": "NG",
        "p25": Decimal("18"),
        "p50": Decimal("27.5"),
        "p75": Decimal("36"),
        "sample_size": 40,
        "source": "fixture",
        "as_of_date": "2026-01-01",
    }


_AUDITABLE = {
    "description": {"value": "Last-mile delivery for Lagos pharmacies."},
    "business_model": {"value": "Per-delivery fee plus a subscription."},
    "team_size": {"value": 10},
    "monthly_revenue_minor": {"value": 5_000_000},
    "monthly_costs_minor": {"value": 4_000_000},
    "cash_on_hand_minor": {"value": 20_000_000},
}


@requires_database
class TestBenchmarkWritesRequireMfa:
    async def test_unenrolled_admin_cannot_create(
        self, db_session: AsyncSession
    ) -> None:
        _, admin = await _register_admin(db_session, mfa_enabled=False)

        with pytest.raises(ForbiddenError, match=MFA_MESSAGE):
            await audit.create_benchmark(db_session, admin, _band())

    async def test_enrolled_admin_can_create(self, db_session: AsyncSession) -> None:
        _, admin = await _register_admin(db_session, mfa_enabled=True)

        created = await audit.create_benchmark(db_session, admin, _band())

        assert created.metric is BenchmarkMetric.GROSS_MARGIN_PERCENT


@requires_database
class TestRevealRequiresMfa:
    async def _approved_interest(
        self, session: AsyncSession
    ) -> tuple[CurrentUser, uuid.UUID]:
        founder_user = await identity.register_user(
            session,
            email=f"founder-{uuid.uuid4().hex}@example.test",
            password=PASSWORD,
            role=Role.FOUNDER,
            first_name="Ada",
            last_name="Founder",
        )
        assert founder_user is not None
        founder_user.status = AccountStatus.ACTIVE
        await session.flush()
        founder = CurrentUser(
            id=founder_user.id,
            role=Role.FOUNDER,
            status=AccountStatus.ACTIVE,
            email_verified=True,
        )
        profile = await intake.create_profile(
            session,
            founder,
            {
                "name": "Kanmi Pay",
                "sector": "fintech",
                "stage": Stage.SEED,
                "country": "NG",
                "currency": "NGN",
                "fields": dict(_AUDITABLE),
            },
        )
        run, _ = await audit.request_audit(session, founder, profile.id)
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
        run.status = AuditStatus.SUCCEEDED
        run.report = report_to_storage(report)
        await intake.set_discoverability(session, founder, profile.id, visible=True)

        investor_user = await identity.register_user(
            session,
            email=f"inv-{uuid.uuid4().hex}@example.test",
            password=PASSWORD,
            role=Role.INVESTOR,
            first_name="Ida",
            last_name="Investor",
        )
        assert investor_user is not None
        investor_user.status = AccountStatus.ACTIVE
        await session.flush()
        investor = CurrentUser(
            id=investor_user.id,
            role=Role.INVESTOR,
            status=AccountStatus.ACTIVE,
            email_verified=True,
        )
        enrolled_admin = await _register_admin(session, mfa_enabled=True)
        interest = await brokerage.express_interest(session, investor, profile.id)
        await brokerage.decide_interest(
            session, enrolled_admin[1], interest.id, approve=True
        )
        return founder, interest.id

    async def test_unenrolled_admin_cannot_reveal(
        self, db_session: AsyncSession
    ) -> None:
        _, interest_id = await self._approved_interest(db_session)
        _, unenrolled = await _register_admin(db_session, mfa_enabled=False)

        with pytest.raises(ForbiddenError, match=MFA_MESSAGE):
            await brokerage.reveal_report(db_session, unenrolled, interest_id)

    async def test_enrolled_admin_can_reveal(self, db_session: AsyncSession) -> None:
        _, interest_id = await self._approved_interest(db_session)
        _, enrolled = await _register_admin(db_session, mfa_enabled=True)

        reveal = await brokerage.reveal_report(db_session, enrolled, interest_id)

        assert reveal.interest_id == interest_id


@requires_database
class TestReopenRequiresMfa:
    async def _open_task(self, session: AsyncSession) -> uuid.UUID:
        user = await identity.register_user(
            session,
            email=f"founder-{uuid.uuid4().hex}@example.test",
            password=PASSWORD,
            role=Role.FOUNDER,
            first_name="Ada",
            last_name="Founder",
        )
        assert user is not None
        user.status = AccountStatus.ACTIVE
        await session.flush()
        actor = CurrentUser(
            id=user.id,
            role=Role.FOUNDER,
            status=AccountStatus.ACTIVE,
            email_verified=True,
        )
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
        task = ReadinessTask(
            startup_id=profile.id,
            owner_id=user.id,
            dimension="traction",
            action="Publish a pricing page.",
            action_fingerprint=uuid.uuid4().hex * 2,
            requirement=Requirement.REQUIRED,
            status=TaskStatus.FAILED,
            assessment_attempts=3,
        )
        session.add(task)
        await session.flush()
        return task.id

    async def test_unenrolled_admin_cannot_reopen(
        self, db_session: AsyncSession
    ) -> None:
        task_id = await self._open_task(db_session)
        _, unenrolled = await _register_admin(db_session, mfa_enabled=False)

        with pytest.raises(ForbiddenError, match=MFA_MESSAGE):
            await readiness.reopen_task(db_session, unenrolled, task_id)

    async def test_enrolled_admin_can_reopen(self, db_session: AsyncSession) -> None:
        task_id = await self._open_task(db_session)
        _, enrolled = await _register_admin(db_session, mfa_enabled=True)

        reopened = await readiness.reopen_task(db_session, enrolled, task_id)

        assert reopened.assessment_attempts == 0
        assert reopened.status is TaskStatus.OPEN


@requires_database
class TestAdminReportRequiresMfa:
    """The admin-tier report check lives in the router (T4.2), now via assert_admin."""

    async def _succeeded_run(
        self, session: AsyncSession
    ) -> tuple[uuid.UUID, uuid.UUID]:
        user = await identity.register_user(
            session,
            email=f"founder-{uuid.uuid4().hex}@example.test",
            password=PASSWORD,
            role=Role.FOUNDER,
            first_name="Ada",
            last_name="Founder",
        )
        assert user is not None
        user.status = AccountStatus.ACTIVE
        await session.flush()
        owner = CurrentUser(
            id=user.id,
            role=Role.FOUNDER,
            status=AccountStatus.ACTIVE,
            email_verified=True,
        )
        profile = await intake.create_profile(
            session,
            owner,
            {
                "name": "Kanmi Pay",
                "sector": "fintech",
                "stage": Stage.SEED,
                "country": "NG",
                "currency": "NGN",
                "fields": dict(_AUDITABLE),
            },
        )
        run, _ = await audit.request_audit(session, owner, profile.id)
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
        run.status = AuditStatus.SUCCEEDED
        run.report = report_to_storage(report)
        await session.flush()
        return profile.id, run.id

    async def test_unenrolled_admin_cannot_read_admin_report(
        self, db_session: AsyncSession
    ) -> None:
        startup_id, run_id = await self._succeeded_run(db_session)
        _, unenrolled = await _register_admin(db_session, mfa_enabled=False)

        with pytest.raises(ForbiddenError, match=MFA_MESSAGE):
            await read_audit_report_as_admin(startup_id, run_id, unenrolled, db_session)

    async def test_enrolled_admin_can_read_admin_report(
        self, db_session: AsyncSession
    ) -> None:
        startup_id, run_id = await self._succeeded_run(db_session)
        _, enrolled = await _register_admin(db_session, mfa_enabled=True)

        report = await read_audit_report_as_admin(
            startup_id, run_id, enrolled, db_session
        )

        assert report.rubric_version == "v1"


# ---------------------------------------------------------------------------
# Real HTTP path -- CurrentAdmin on a production admin route
# ---------------------------------------------------------------------------


@requires_database
class TestProductionAdminRouteRefusesUnenrolledAdmin:
    """Go through the real FastAPI app so the dependency swap is exercised.

    Calling a route function as Python skips `Depends`. Hitting the ASGI app
    is the only way to prove `CurrentAdmin` stands between an unenrolled
    admin token and the handler.
    """

    @pytest.fixture
    async def client(self, db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
        from app.main import app

        async def _session() -> AsyncIterator[AsyncSession]:
            yield db_session

        async def _load(user_id: uuid.UUID) -> CurrentUser | None:
            return await identity.load_current_user(db_session, user_id)

        app.dependency_overrides[get_session] = _session
        set_user_loader(_load)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as http:
                yield http
        finally:
            app.dependency_overrides.clear()
            set_user_loader(None)

    async def test_benchmark_create_over_http_refuses_unenrolled_admin(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user, _ = await _register_admin(db_session, mfa_enabled=False)
        token = create_access_token(user.id, Role.ADMIN, settings=get_settings())

        response = await client.post(
            "/v1/benchmarks",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "sector": "logistics",
                "stage": "seed",
                "metric": "gross_margin_percent",
                "region": "NG",
                "p25": "18",
                "p50": "27.5",
                "p75": "36",
                "sample_size": 40,
                "source": "fixture",
                "as_of_date": "2026-01-01",
            },
        )

        assert response.status_code == 403
        body = response.json()
        assert body["error"]["code"] == ErrorCode.FORBIDDEN
        assert MFA_MESSAGE in body["error"]["message"]

    async def test_benchmark_create_over_http_allows_enrolled_admin(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user, _ = await _register_admin(db_session, mfa_enabled=True)
        token = create_access_token(user.id, Role.ADMIN, settings=get_settings())

        response = await client.post(
            "/v1/benchmarks",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "sector": "logistics",
                "stage": "seed",
                "metric": "gross_margin_percent",
                "region": "NG",
                "p25": "18",
                "p50": "27.5",
                "p75": "36",
                "sample_size": 40,
                "source": "fixture",
                "as_of_date": "2026-01-01",
            },
        )

        assert response.status_code == 201, response.text
