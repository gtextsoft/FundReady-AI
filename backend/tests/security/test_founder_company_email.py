"""Founders register with a company address, and it names their profile.

`DECISIONS.md` **D20**, `AUTH.md` §3.2. Two rules that meet here:

* a founder signing up on a consumer mailbox is refused, openly, with a
  machine-readable reason the mobile client can show against the email field
* the company domain they *do* verify becomes the first name on their Startup
  Profile -- only when they did not supply one

Also pins the role gate on profile creation. `AUTH.md` §5's permission matrix
gives "create/edit own startup" to founders and admins and denies it to
investors, but the endpoint asked only for an *active account* -- so any
investor could create one. Found while wiring the domain rule; fixed by the
`require_role` change on the route, not by the domain rule itself.
"""

import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import InvalidRequestError
from app.core.security import (
    AccountStatus,
    CurrentUser,
    Role,
    create_access_token,
    set_user_loader,
)
from app.modules.identity import service as identity
from app.modules.identity.models import User
from app.modules.identity.repository import UserRepository
from app.modules.intake import service as intake
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


def consumer_email() -> str:
    return f"founder-{uuid.uuid4().hex}@gmail.com"


def actor_for(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        role=user.role,
        status=AccountStatus.ACTIVE,
        email_verified=True,
        mfa_enabled=user.mfa_enabled,
    )


async def activated(session: AsyncSession, email: str, role: Role) -> User:
    """A registered, verified account -- the state profile creation requires."""
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
    # `email_verified` is derived from the timestamp, not stored separately.
    user.email_verified_at = datetime.now(UTC)
    await session.flush()
    return user


class TestFoundersNeedACompanyAddress:
    async def test_a_consumer_address_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        with pytest.raises(InvalidRequestError):
            await identity.register_user(
                db_session,
                email=consumer_email(),
                password=PASSWORD,
                role=Role.FOUNDER,
                first_name="Ada",
                last_name="Tester",
            )

    async def test_the_refusal_says_which_field_and_why(
        self, db_session: AsyncSession
    ) -> None:
        """The client shows this against the email input, not as a toast."""
        with pytest.raises(InvalidRequestError) as refusal:
            await identity.register_user(
                db_session,
                email=consumer_email(),
                password=PASSWORD,
                role=Role.FOUNDER,
                first_name="Ada",
                last_name="Tester",
            )

        assert refusal.value.status_code == 422
        assert refusal.value.details == {
            "field": "email",
            "reason": "consumer_email_domain",
        }

    async def test_a_company_address_is_accepted(
        self, db_session: AsyncSession
    ) -> None:
        user = await identity.register_user(
            db_session,
            email=company_email(),
            password=PASSWORD,
            role=Role.FOUNDER,
            first_name="Ada",
            last_name="Tester",
        )

        assert user is not None
        assert user.role is Role.FOUNDER

    async def test_case_and_whitespace_do_not_evade_it(
        self, db_session: AsyncSession
    ) -> None:
        with pytest.raises(InvalidRequestError):
            await identity.register_user(
                db_session,
                email=f"  Founder-{uuid.uuid4().hex}@GMAIL.COM  ",
                password=PASSWORD,
                role=Role.FOUNDER,
                first_name="Ada",
                last_name="Tester",
            )

    async def test_a_consumer_subdomain_does_not_evade_it(
        self, db_session: AsyncSession
    ) -> None:
        with pytest.raises(InvalidRequestError):
            await identity.register_user(
                db_session,
                email=f"founder-{uuid.uuid4().hex}@mail.gmail.com",
                password=PASSWORD,
                role=Role.FOUNDER,
                first_name="Ada",
                last_name="Tester",
            )

    async def test_no_account_is_left_behind(self, db_session: AsyncSession) -> None:
        """Refused before anything is written, so a retry is not a duplicate."""
        email = consumer_email()

        with pytest.raises(InvalidRequestError):
            await identity.register_user(
                db_session,
                email=email,
                password=PASSWORD,
                role=Role.FOUNDER,
                first_name="Ada",
                last_name="Tester",
            )

        assert await UserRepository(db_session).get_by_email(email) is None

    async def test_investors_are_not_restricted(self, db_session: AsyncSession) -> None:
        """An angel investing personally has no company domain to give."""
        user = await identity.register_user(
            db_session,
            email=consumer_email(),
            password=PASSWORD,
            role=Role.INVESTOR,
            first_name="Ada",
            last_name="Tester",
        )

        assert user is not None
        assert user.role is Role.INVESTOR


class TestTheDomainNamesTheProfile:
    async def test_the_name_is_read_from_the_domain(
        self, db_session: AsyncSession
    ) -> None:
        user = await activated(db_session, company_email("acme.com"), Role.FOUNDER)

        profile = await intake.create_profile(db_session, actor_for(user), {})

        assert profile.name == "Acme"

    async def test_a_supplied_name_is_never_overwritten(
        self, db_session: AsyncSession
    ) -> None:
        """The founder's own words beat a guess off their email."""
        user = await activated(db_session, company_email("acme.com"), Role.FOUNDER)

        profile = await intake.create_profile(
            db_session, actor_for(user), {"name": "Kanmi Logistics"}
        )

        assert profile.name == "Kanmi Logistics"

    async def test_a_public_suffix_is_not_mistaken_for_the_company(
        self, db_session: AsyncSession
    ) -> None:
        user = await activated(db_session, company_email("kanmi.com.ng"), Role.FOUNDER)

        profile = await intake.create_profile(db_session, actor_for(user), {})

        assert profile.name == "Kanmi"

    async def test_the_derived_name_can_be_corrected(
        self, db_session: AsyncSession
    ) -> None:
        """It is a prefill, so the normal update path must move it."""
        user = await activated(db_session, company_email("acme.com"), Role.FOUNDER)
        actor = actor_for(user)
        profile = await intake.create_profile(db_session, actor, {})

        updated = await intake.update_profile(
            db_session, actor, profile.id, {"name": "Acme Robotics Ltd"}
        )

        assert updated.name == "Acme Robotics Ltd"

    async def test_an_admin_domain_never_names_a_startup(
        self, db_session: AsyncSession
    ) -> None:
        """An admin may create a profile (AUTH.md section 5). Deriving from
        their address would stamp a SACI domain onto a startup."""
        user = await activated(db_session, company_email("saci.com"), Role.FOUNDER)
        user.role = Role.ADMIN
        await db_session.flush()

        profile = await intake.create_profile(db_session, actor_for(user), {})

        assert profile.name is None

    async def test_an_investor_domain_yields_no_name(
        self, db_session: AsyncSession
    ) -> None:
        """Investors may hold consumer addresses; "Gmail" is never a company."""
        user = await activated(db_session, consumer_email(), Role.INVESTOR)

        profile = await intake.create_profile(db_session, actor_for(user), {})

        assert profile.name is None
        assert "name" in intake.missing_fields(profile)


class TestProfileCreationIsAFounderCapability:
    """`AUTH.md` §5 grants this to founders. It was open to any active account."""

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

    async def test_an_investor_cannot_create_a_startup_profile(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await activated(db_session, consumer_email(), Role.INVESTOR)
        token = create_access_token(user.id, Role.INVESTOR)

        response = await client.post(
            "/v1/startups",
            json={"name": "Not mine to make"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403

    async def test_a_founder_still_can(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await activated(db_session, company_email("acme.com"), Role.FOUNDER)
        token = create_access_token(user.id, Role.FOUNDER)

        response = await client.post(
            "/v1/startups",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
        assert response.json()["name"] == "Acme"

    async def test_the_registration_rejection_is_a_422_on_the_wire(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/v1/auth/register",
            json={
                "email": consumer_email(),
                "password": PASSWORD,
                "role": "founder",
                # Valid, so the only thing wrong with this request is the
                # address. Without them the body fails schema validation first
                # and returns a *different* 422 -- the assertion below would be
                # checking that a missing name is reported, not the domain rule.
                "first_name": "Ada",
                "last_name": "Tester",
            },
        )

        assert response.status_code == 422
        body = response.json()["error"]
        assert body["details"] == {
            "field": "email",
            "reason": "consumer_email_domain",
        }
