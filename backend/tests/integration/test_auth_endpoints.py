"""The auth endpoints as the mobile client will actually call them.

The service tests cover the security logic; these cover the contract -- status
codes, response shapes, and the dependency wiring that only exists once a
request goes through the real application.
"""

import uuid
from collections.abc import AsyncIterator, Iterator

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.security import CurrentUser, set_user_loader
from app.modules.identity import service
from tests.conftest import requires_database

pytestmark = [pytest.mark.integration, requires_database]

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-signing-key-at-least-32-characters")
    monkeypatch.setenv("ARGON2_MEMORY_COST_KIB", "8192")
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """The real app, with its session replaced by the rolled-back one.

    An ASGI transport rather than `TestClient` so the app runs on the same
    event loop as the database fixture.
    """
    from app.main import app

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _load(user_id: uuid.UUID) -> CurrentUser | None:
        return await service.load_current_user(db_session, user_id)

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


def unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.test"


# Spread into every registration body below. The tests that assert a 422 need
# these too: without them the request is invalid for a *second* reason, and a
# test checking "admin role is rejected" would pass on a missing name instead.
NAMES = {"first_name": "Ada", "last_name": "Tester"}


async def register(client: AsyncClient, email: str, role: str = "founder") -> None:
    response = await client.post(
        "/v1/auth/register",
        json={"email": email, "password": PASSWORD, "role": role, **NAMES},
    )
    assert response.status_code == 202, response.text


async def login(client: AsyncClient, email: str) -> dict[str, str]:
    """Log in and return the token pair.

    Since T1.2c the response is discriminated: `status` says whether tokens are
    present or a second factor is outstanding. This helper covers the
    no-MFA path.
    """
    response = await client.post(
        "/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "authenticated", body
    return dict(body["tokens"])


class TestRegisterEndpoint:
    async def test_accepts_a_new_founder(self, client: AsyncClient) -> None:
        response = await client.post(
            "/v1/auth/register",
            json={
                "email": unique_email(),
                "password": PASSWORD,
                "role": "founder",
                **NAMES,
            },
        )

        assert response.status_code == 202
        assert response.json()["status"] == "pending_verification"

    async def test_duplicate_returns_an_identical_response(
        self, client: AsyncClient
    ) -> None:
        """Byte-for-byte identical, or the endpoint leaks who has an account."""
        email = unique_email()
        body = {"email": email, "password": PASSWORD, "role": "founder", **NAMES}

        first = await client.post("/v1/auth/register", json=body)
        second = await client.post("/v1/auth/register", json=body)

        assert first.status_code == second.status_code == 202
        assert first.json() == second.json()

    async def test_admin_role_is_rejected_by_the_schema(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/v1/auth/register",
            json={
                "email": unique_email(),
                "password": PASSWORD,
                "role": "admin",
                **NAMES,
            },
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    async def test_unknown_fields_are_rejected(self, client: AsyncClient) -> None:
        response = await client.post(
            "/v1/auth/register",
            json={
                "email": unique_email(),
                "password": PASSWORD,
                "role": "founder",
                **NAMES,
                "status": "active",  # an attempt to set your own status
            },
        )

        assert response.status_code == 422

    async def test_the_password_is_not_echoed(self, client: AsyncClient) -> None:
        """A rejected password must not come back in the error body."""
        # Distinctive enough that it cannot collide with pydantic's own error
        # vocabulary -- "short" would match `string_too_short` and pass falsely.
        rejected = "xyzzy42"

        response = await client.post(
            "/v1/auth/register",
            json={
                "email": unique_email(),
                "password": rejected,
                "role": "founder",
                **NAMES,
            },
        )

        assert response.status_code == 422
        assert rejected not in response.text


class TestLoginEndpoint:
    async def test_returns_a_token_pair(self, client: AsyncClient) -> None:
        email = unique_email()
        await register(client, email)

        tokens = await login(client, email)

        assert tokens["token_type"] == "bearer"
        assert tokens["access_token"] and tokens["refresh_token"]
        assert tokens["expires_in"] > 0

    async def test_no_mfa_token_when_mfa_is_off(self, client: AsyncClient) -> None:
        """The two branches are mutually exclusive, not both populated."""
        email = unique_email()
        await register(client, email)

        body = (
            await client.post(
                "/v1/auth/login", json={"email": email, "password": PASSWORD}
            )
        ).json()

        assert body["status"] == "authenticated"
        assert body["mfa_token"] is None

    async def test_wrong_password_is_401(self, client: AsyncClient) -> None:
        email = unique_email()
        await register(client, email)

        response = await client.post(
            "/v1/auth/login", json={"email": email, "password": "wrong-password-here"}
        )

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthenticated"

    async def test_unknown_account_gives_the_same_response(
        self, client: AsyncClient
    ) -> None:
        email = unique_email()
        await register(client, email)

        wrong = await client.post(
            "/v1/auth/login", json={"email": email, "password": "wrong-password-here"}
        )
        missing = await client.post(
            "/v1/auth/login",
            json={"email": unique_email(), "password": "wrong-password-here"},
        )

        assert wrong.status_code == missing.status_code
        assert wrong.json() == missing.json()


class TestMeEndpoint:
    async def test_requires_a_token(self, client: AsyncClient) -> None:
        response = await client.get("/v1/users/me")

        assert response.status_code == 401

    async def test_returns_the_callers_own_account(self, client: AsyncClient) -> None:
        email = unique_email()
        await register(client, email)
        tokens = await login(client, email)

        response = await client.get(
            "/v1/users/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["email"] == email
        assert body["role"] == "founder"
        assert body["status"] == "pending_verification"

    @pytest.mark.parametrize("role", ["founder", "investor"])
    async def test_the_registered_name_survives_the_round_trip(
        self, client: AsyncClient, role: str
    ) -> None:
        """Registration -> storage -> response, over HTTP.

        The service-level test proves `register_user` saves the name; this
        proves the router actually hands it over. Dropping
        `first_name=payload.first_name` in the route would leave every other
        test passing and silently store `null`.
        """
        email = unique_email()
        response = await client.post(
            "/v1/auth/register",
            json={
                "email": email,
                "password": PASSWORD,
                "role": role,
                "first_name": "Amaka",
                "last_name": "Okonkwo",
            },
        )
        assert response.status_code == 202, response.text
        tokens = await login(client, email)

        me = await client.get(
            "/v1/users/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        assert me.status_code == 200
        body = me.json()
        assert body["first_name"] == "Amaka"
        assert body["last_name"] == "Okonkwo"
        assert body["role"] == role

    async def test_never_exposes_the_password_hash(self, client: AsyncClient) -> None:
        email = unique_email()
        await register(client, email)
        tokens = await login(client, email)

        response = await client.get(
            "/v1/users/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        assert "password" not in response.text.lower()
        assert "argon2" not in response.text.lower()


class TestRefreshEndpoint:
    async def test_rotates_the_pair(self, client: AsyncClient) -> None:
        email = unique_email()
        await register(client, email)
        first = await login(client, email)

        response = await client.post(
            "/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
        )

        assert response.status_code == 200
        assert response.json()["refresh_token"] != first["refresh_token"]

    async def test_replay_ends_the_session(self, client: AsyncClient) -> None:
        email = unique_email()
        await register(client, email)
        first = await login(client, email)
        second = await client.post(
            "/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
        )
        assert second.status_code == 200

        replay = await client.post(
            "/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
        )
        after = await client.post(
            "/v1/auth/refresh",
            json={"refresh_token": second.json()["refresh_token"]},
        )

        assert replay.status_code == 401
        assert after.status_code == 401, "the successor dies with the family"


class TestLogoutEndpoint:
    async def test_revokes_the_session(self, client: AsyncClient) -> None:
        email = unique_email()
        await register(client, email)
        tokens = await login(client, email)

        logout = await client.post(
            "/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
        )
        reuse = await client.post(
            "/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

        assert logout.status_code == 204
        assert reuse.status_code == 401

    async def test_unknown_token_still_returns_204(self, client: AsyncClient) -> None:
        response = await client.post(
            "/v1/auth/logout", json={"refresh_token": "never-issued"}
        )

        assert response.status_code == 204


class TestMfaOverHttp:
    async def test_enrolment_requires_a_token(self, client: AsyncClient) -> None:
        assert (await client.post("/v1/auth/mfa/enroll")).status_code == 401

    async def test_the_full_enrol_then_challenge_flow(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Once MFA is on, the password alone stops returning tokens."""
        monkeypatch.setenv(
            "MFA_SECRET_ENCRYPTION_KEY", "a-dev-mfa-key-32-characters-long!!"
        )
        get_settings.cache_clear()

        email = unique_email()
        await register(client, email)
        tokens = await login(client, email)
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        enrolment = await client.post("/v1/auth/mfa/enroll", headers=headers)
        assert enrolment.status_code == 200
        secret = enrolment.json()["secret"]
        assert "otpauth://" in enrolment.json()["provisioning_uri"]

        confirm = await client.post(
            "/v1/auth/mfa/confirm",
            headers=headers,
            json={"code": pyotp.TOTP(secret, digits=6, interval=30).now()},
        )
        assert confirm.status_code == 200
        recovery_codes = confirm.json()["recovery_codes"]
        assert len(recovery_codes) == 10

        # Password alone is no longer enough.
        challenged = await client.post(
            "/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        body = challenged.json()
        assert body["status"] == "mfa_required"
        assert body["tokens"] is None
        assert body["mfa_token"]

        # The challenge token is not usable as an access token.
        as_access = await client.get(
            "/v1/users/me",
            headers={"Authorization": f"Bearer {body['mfa_token']}"},
        )
        assert as_access.status_code == 401

        # A recovery code completes it (the TOTP step was just consumed).
        verified = await client.post(
            "/v1/auth/mfa/verify",
            json={"mfa_token": body["mfa_token"], "code": recovery_codes[0]},
        )
        assert verified.status_code == 200
        assert verified.json()["access_token"]

        # And that recovery code is now spent.
        replayed = await client.post(
            "/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        again = await client.post(
            "/v1/auth/mfa/verify",
            json={
                "mfa_token": replayed.json()["mfa_token"],
                "code": recovery_codes[0],
            },
        )
        assert again.status_code == 401
