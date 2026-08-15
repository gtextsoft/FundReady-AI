"""Product catalogue authz, listing, enrolment, and gap matching (T3.2)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import ForbiddenError, InvalidRequestError, NotFoundError
from app.core.security import (
    AccountStatus,
    CurrentUser,
    Role,
    create_access_token,
    set_user_loader,
)
from app.modules.audit.rubric.v1 import Dimension
from app.modules.commerce import service
from app.modules.commerce.models import ProductKind
from app.modules.commerce.schemas import ProductCreate
from app.modules.identity import service as identity
from app.modules.identity.models import User
from app.modules.intake import service as intake
from app.modules.readiness.generation import Requirement, TaskStatus
from app.modules.readiness.models import ReadinessTask
from tests.conftest import requires_database

pytestmark = [pytest.mark.security, pytest.mark.integration, requires_database]

PASSWORD = "correct-horse-battery-staple"
MFA_MESSAGE = "Admin accounts must enrol in two-factor authentication first."


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-signing-key-at-least-32-characters")
    monkeypatch.setenv("ARGON2_MEMORY_COST_KIB", "8192")
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _actor(user: User, *, mfa_enabled: bool | None = None) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        role=user.role,
        status=user.status,
        email_verified=True,
        mfa_enabled=user.mfa_enabled if mfa_enabled is None else mfa_enabled,
    )


async def _founder(session: AsyncSession) -> User:
    user = await identity.register_user(
        session,
        email=f"founder-{uuid.uuid4().hex}@kanmi-logistics.com",
        password=PASSWORD,
        role=Role.FOUNDER,
        first_name="Ada",
        last_name="Founder",
    )
    assert user is not None
    user.status = AccountStatus.ACTIVE
    user.email_verified_at = datetime.now(UTC)
    await session.flush()
    return user


async def _admin(session: AsyncSession, *, mfa_enabled: bool) -> User:
    user = await identity.register_user(
        session,
        email=f"admin-{uuid.uuid4().hex}@saci.test",
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
    return user


async def _product(
    session: AsyncSession,
    admin: User,
    **overrides: object,
) -> object:
    payload = ProductCreate(
        kind=ProductKind.PROGRAM,
        slug=f"clinic-{uuid.uuid4().hex[:8]}",
        title="Unit economics clinic",
        description="Pricing and CAC.",
        regions=["*"],
        gap_tags=["unit_economics"],
        active=True,
    )
    data = payload.model_dump()
    data.update(overrides)
    return await service.create_product(
        session, _actor(admin, mfa_enabled=True), ProductCreate.model_validate(data)
    )


@requires_database
class TestCatalogueService:
    async def test_unenrolled_admin_cannot_create(
        self, db_session: AsyncSession
    ) -> None:
        admin = await _admin(db_session, mfa_enabled=False)
        with pytest.raises(ForbiddenError) as exc:
            await service.create_product(
                db_session,
                _actor(admin),
                ProductCreate(
                    kind=ProductKind.PROGRAM,
                    slug="clinic",
                    title="Clinic",
                    regions=["*"],
                ),
            )
        assert MFA_MESSAGE in exc.value.message

    async def test_founder_cannot_create(self, db_session: AsyncSession) -> None:
        founder = await _founder(db_session)
        with pytest.raises(ForbiddenError):
            await service.create_product(
                db_session,
                _actor(founder),
                ProductCreate(
                    kind=ProductKind.PROGRAM,
                    slug="clinic",
                    title="Clinic",
                    regions=["*"],
                ),
            )

    async def test_founder_list_hides_retired(self, db_session: AsyncSession) -> None:
        admin = await _admin(db_session, mfa_enabled=True)
        founder = await _founder(db_session)
        live = await _product(db_session, admin, slug=f"live-{uuid.uuid4().hex[:8]}")
        retired = await _product(
            db_session, admin, slug=f"old-{uuid.uuid4().hex[:8]}", active=False
        )

        page = await service.list_products(db_session, _actor(founder), limit=100)
        ids = {item.id for item in page.items}
        assert live.id in ids
        assert retired.id not in ids

    async def test_region_filter(self, db_session: AsyncSession) -> None:
        admin = await _admin(db_session, mfa_enabled=True)
        founder = await _founder(db_session)
        ng = await _product(
            db_session, admin, slug=f"ng-{uuid.uuid4().hex[:8]}", regions=["NG"]
        )
        gb = await _product(
            db_session, admin, slug=f"gb-{uuid.uuid4().hex[:8]}", regions=["GB"]
        )
        page = await service.list_products(
            db_session, _actor(founder), region="NG", limit=100
        )
        ids = {item.id for item in page.items}
        assert ng.id in ids
        assert gb.id not in ids

    async def test_enrol_is_idempotent_and_founder_only(
        self, db_session: AsyncSession
    ) -> None:
        admin = await _admin(db_session, mfa_enabled=True)
        founder = await _founder(db_session)
        other = await _founder(db_session)
        product = await _product(db_session, admin)

        first = await service.enrol_product(db_session, _actor(founder), product.id)
        second = await service.enrol_product(db_session, _actor(founder), product.id)
        assert first.status == "enrolled"
        assert second.status == "enrolled"

        with pytest.raises(ForbiddenError):
            await service.enrol_product(db_session, _actor(admin), product.id)

        mine = await service.list_enrolments(db_session, _actor(founder))
        theirs = await service.list_enrolments(db_session, _actor(other))
        assert mine.total == 1
        assert theirs.total == 0

    async def test_paid_without_price_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        admin = await _admin(db_session, mfa_enabled=True)
        founder = await _founder(db_session)
        product = await _product(
            db_session,
            admin,
            slug=f"paid-{uuid.uuid4().hex[:8]}",
            amount_minor=25000,
            currency="USD",
        )
        with pytest.raises(InvalidRequestError) as exc:
            await service.enrol_product(db_session, _actor(founder), product.id)
        assert exc.value.details is not None
        assert exc.value.details["reason"] == "checkout_not_configured"

    async def test_recommendations_match_open_gaps_and_country(
        self, db_session: AsyncSession
    ) -> None:
        admin = await _admin(db_session, mfa_enabled=True)
        founder = await _founder(db_session)
        profile = await intake.create_profile(
            db_session, _actor(founder), {"country": "NG"}
        )
        matched = await _product(
            db_session,
            admin,
            slug=f"ue-{uuid.uuid4().hex[:8]}",
            regions=["NG"],
            gap_tags=["unit_economics"],
        )
        other_gap = await _product(
            db_session,
            admin,
            slug=f"team-{uuid.uuid4().hex[:8]}",
            regions=["NG"],
            gap_tags=["team"],
        )
        other_region = await _product(
            db_session,
            admin,
            slug=f"gb-{uuid.uuid4().hex[:8]}",
            regions=["GB"],
            gap_tags=["unit_economics"],
        )
        browse_only = await _product(
            db_session,
            admin,
            slug=f"open-{uuid.uuid4().hex[:8]}",
            regions=["*"],
            gap_tags=[],
        )
        db_session.add(
            ReadinessTask(
                startup_id=profile.id,
                owner_id=founder.id,
                dimension=Dimension.UNIT_ECONOMICS,
                action="State CAC and the period it was measured over.",
                action_fingerprint="fp-ue-1",
                requirement=Requirement.REQUIRED,
                status=TaskStatus.OPEN,
            )
        )
        await db_session.flush()

        page = await service.list_recommendations(
            db_session, _actor(founder), profile.id, limit=50
        )
        ids = {item.id for item in page.items}
        assert matched.id in ids
        assert other_gap.id not in ids
        assert other_region.id not in ids
        assert browse_only.id not in ids

    async def test_recommendations_are_not_an_idor(
        self, db_session: AsyncSession
    ) -> None:
        admin = await _admin(db_session, mfa_enabled=True)
        owner = await _founder(db_session)
        stranger = await _founder(db_session)
        profile = await intake.create_profile(db_session, _actor(owner), {})
        await _product(db_session, admin)
        with pytest.raises(NotFoundError):
            await service.list_recommendations(db_session, _actor(stranger), profile.id)


@requires_database
class TestCatalogueHttp:
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

    async def test_list_is_404_without_the_route_regression(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        founder = await _founder(db_session)
        token = create_access_token(founder.id, Role.FOUNDER, settings=get_settings())
        response = await client.get(
            "/v1/products", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0

    async def test_create_over_http_refuses_unenrolled_admin(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin(db_session, mfa_enabled=False)
        token = create_access_token(admin.id, Role.ADMIN, settings=get_settings())
        response = await client.post(
            "/v1/admin/products",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "kind": "program",
                "slug": "clinic",
                "title": "Clinic",
                "regions": ["*"],
            },
        )
        assert response.status_code == 403
        assert MFA_MESSAGE in response.json()["error"]["message"]

    async def test_create_and_list_over_http(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin(db_session, mfa_enabled=True)
        founder = await _founder(db_session)
        admin_token = create_access_token(admin.id, Role.ADMIN, settings=get_settings())
        founder_token = create_access_token(
            founder.id, Role.FOUNDER, settings=get_settings()
        )
        created = await client.post(
            "/v1/admin/products",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "kind": "program",
                "slug": f"clinic-{uuid.uuid4().hex[:8]}",
                "title": "Unit economics clinic",
                "description": "Pricing.",
                "regions": ["*"],
                "gap_tags": ["unit_economics"],
                "active": True,
            },
        )
        assert created.status_code == 201, created.text
        product_id = created.json()["id"]

        listed = await client.get(
            "/v1/products?limit=100",
            headers={"Authorization": f"Bearer {founder_token}"},
        )
        assert listed.status_code == 200
        assert any(item["id"] == product_id for item in listed.json()["items"])

        retired = await client.patch(
            f"/v1/admin/products/{product_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"active": False},
        )
        assert retired.status_code == 200
        assert retired.json()["active"] is False

        listed_after = await client.get(
            "/v1/products?limit=100",
            headers={"Authorization": f"Bearer {founder_token}"},
        )
        assert all(item["id"] != product_id for item in listed_after.json()["items"])
