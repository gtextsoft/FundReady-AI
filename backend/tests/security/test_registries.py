"""Company registry reference data and the endpoint that serves it (T1.6)."""

import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.security import (
    AccountStatus,
    Role,
    create_access_token,
    set_user_loader,
)
from app.modules.identity import service as identity
from app.modules.identity.models import User
from app.modules.intake.documents import DocumentKind
from app.modules.intake.registries import REGISTRIES, registry_for
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


def company_email(domain: str = "kanmi-logistics.com") -> str:
    return f"founder-{uuid.uuid4().hex}@{domain}"


async def activated(session: AsyncSession, email: str, role: Role) -> User:
    user = await identity.register_user(
        session,
        email=email,
        password=PASSWORD,
        role=role,
        first_name="Ada",
        last_name="Tester",
    )
    assert user is not None
    user.status = AccountStatus.ACTIVE
    user.email_verified_at = datetime.now(UTC)
    await session.flush()
    return user


class TestRegistryMap:
    def test_nigeria_maps_to_cac(self) -> None:
        entry = registry_for("NG")

        assert entry is not None
        assert entry.short_name == "CAC"
        assert entry.number_label == "RC number"
        assert entry.document_name == "Certificate of Incorporation"

    def test_lookup_is_case_insensitive(self) -> None:
        assert registry_for("ng") == registry_for("NG")

    def test_unknown_country_is_none_not_an_error(self) -> None:
        assert registry_for("ZZ") is None
        assert registry_for(None) is None

    def test_every_entry_carries_the_fields_the_form_needs(self) -> None:
        for country, entry in REGISTRIES.items():
            assert entry.country == country
            assert entry.country_name
            assert entry.registrar
            assert entry.short_name
            assert entry.document_name
            assert entry.number_label
            assert entry.number_example

    def test_registration_certificate_is_a_document_kind(self) -> None:
        assert (
            DocumentKind.REGISTRATION_CERTIFICATE.value
            == "registration_certificate"
        )
        assert len(DocumentKind.REGISTRATION_CERTIFICATE.value) <= 32


class TestRegistriesEndpoint:
    @pytest.fixture
    async def client(
        self, db_session: AsyncSession
    ) -> AsyncIterator[AsyncClient]:
        from app.main import app

        async def _override_session() -> AsyncIterator[AsyncSession]:
            yield db_session

        async def _load(user_id: uuid.UUID):
            return await identity.load_current_user(db_session, user_id)

        app.dependency_overrides[get_session] = _override_session
        set_user_loader(_load)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as http:
                yield http
        finally:
            app.dependency_overrides.clear()
            set_user_loader(None)

    async def test_unauthenticated_callers_are_refused(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/v1/registries")

        assert response.status_code == 401

    async def test_an_authenticated_founder_gets_the_map(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await activated(db_session, company_email("acme.com"), Role.FOUNDER)
        token = create_access_token(user.id, Role.FOUNDER)

        response = await client.get(
            "/v1/registries",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        body = response.json()
        countries = {entry["country"] for entry in body["registries"]}
        assert "NG" in countries
        nigeria = next(e for e in body["registries"] if e["country"] == "NG")
        assert nigeria["short_name"] == "CAC"
