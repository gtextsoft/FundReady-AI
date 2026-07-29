"""Authentication and role enforcement.

These are the tests written first (AGENTS.md section 4). Each case below is a
way a real system has let an unauthenticated or under-privileged caller
through: an unpinned algorithm, a refresh token accepted as an access token, a
role trusted from the token, a revoked session that kept working until expiry.

The contract under test (AUTH.md section 4.3): **401** means the token is
missing, invalid, or expired -- the client refreshes and retries once. **403**
means authenticated but not permitted -- the client must not retry.
"""

import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.deps import (
    CurrentAdmin,
    CurrentFounder,
    CurrentInvestor,
    CurrentUserDep,
)
from app.core.errors import ErrorCode, register_exception_handlers
from app.core.logging import RequestContextMiddleware
from app.core.security import (
    AccountStatus,
    CurrentUser,
    Role,
    TokenType,
    create_access_token,
    set_user_loader,
)

Users = dict[uuid.UUID, CurrentUser]

SIGNING_KEY = "test-signing-key-at-least-32-characters-long"
OTHER_KEY = "a-different-signing-key-32-characters-long"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("JWT_SECRET_KEY", SIGNING_KEY)
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def users() -> Users:
    return {}


@pytest.fixture(autouse=True)
def loader(users: dict[uuid.UUID, CurrentUser]) -> Iterator[None]:
    """Stand in for the repository-backed loader that arrives with T1.2."""

    async def load(user_id: uuid.UUID) -> CurrentUser | None:
        return users.get(user_id)

    set_user_loader(load)
    yield
    set_user_loader(None)


def add_user(
    users: Users,
    role: Role = Role.FOUNDER,
    status: AccountStatus = AccountStatus.ACTIVE,
    session_valid_after: datetime | None = None,
) -> CurrentUser:
    user = CurrentUser(
        id=uuid.uuid4(),
        role=role,
        status=status,
        email_verified=status is AccountStatus.ACTIVE,
        session_valid_after=session_valid_after,
    )
    users[user.id] = user
    return user


@pytest.fixture
def app() -> FastAPI:
    """A minimal app exposing one route per protection level."""
    test_app = FastAPI()
    test_app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(test_app)

    @test_app.get("/any")
    async def any_user(user: CurrentUserDep) -> dict[str, str]:
        return {"id": str(user.id), "role": user.role.value}

    @test_app.get("/founder-only")
    async def founder_only(user: CurrentFounder) -> dict[str, str]:
        return {"id": str(user.id)}

    @test_app.get("/investor-only")
    async def investor_only(user: CurrentInvestor) -> dict[str, str]:
        return {"id": str(user.id)}

    @test_app.get("/admin-only")
    async def admin_only(user: CurrentAdmin) -> dict[str, str]:
        return {"id": str(user.id)}

    return test_app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def error_code(response: Any) -> str:
    body = response.json()
    assert set(body) == {"error"}, "errors always use the documented envelope"
    return str(body["error"]["code"])


def forge(settings: Settings, /, key: str = SIGNING_KEY, **overrides: Any) -> str:
    """Hand-build a token so individual claims can be made hostile."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(uuid.uuid4()),
        "typ": TokenType.ACCESS.value,
        "role": Role.FOUNDER.value,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": uuid.uuid4().hex,
    }
    algorithm = str(overrides.pop("algorithm", settings.jwt_algorithm))
    payload.update(overrides)
    return jwt.encode(payload, key, algorithm=algorithm)


# ---------------------------------------------------------------------------
# 401 -- the token is missing, invalid, or expired
# ---------------------------------------------------------------------------


class TestRejectedTokens:
    def test_no_header(self, settings: Settings, client: TestClient) -> None:
        response = client.get("/any")

        assert response.status_code == 401
        assert error_code(response) == ErrorCode.UNAUTHENTICATED

    @pytest.mark.parametrize(
        "header",
        [
            {"Authorization": "Bearer "},
            {"Authorization": "Bearer not-a-jwt"},
            {"Authorization": "Basic dXNlcjpwYXNz"},
            {"Authorization": "abc.def.ghi"},
        ],
        ids=["empty", "garbage", "wrong-scheme", "no-scheme"],
    )
    def test_malformed_authorization(
        self, settings: Settings, client: TestClient, header: dict[str, str]
    ) -> None:
        assert client.get("/any", headers=header).status_code == 401

    def test_expired_token(
        self, settings: Settings, client: TestClient, users: Users
    ) -> None:
        user = add_user(users)
        token = create_access_token(
            user.id,
            user.role,
            settings=settings,
            issued_at=datetime.now(UTC) - timedelta(hours=2),
            expires_in=timedelta(minutes=15),
        )

        assert client.get("/any", headers=auth(token)).status_code == 401

    def test_token_signed_with_another_key(
        self, settings: Settings, client: TestClient
    ) -> None:
        """A forged signature must not verify."""
        token = forge(settings, key=OTHER_KEY)

        assert client.get("/any", headers=auth(token)).status_code == 401

    def test_alg_none_is_rejected(
        self, settings: Settings, client: TestClient, users: Users
    ) -> None:
        """The classic: strip the signature and declare the token unsigned."""
        user = add_user(users)
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": str(user.id),
                "typ": TokenType.ACCESS.value,
                "role": Role.ADMIN.value,
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=15)).timestamp()),
                "iss": settings.jwt_issuer,
                "aud": settings.jwt_audience,
            },
            key="",
            algorithm="none",
        )

        assert client.get("/any", headers=auth(token)).status_code == 401

    def test_algorithm_confusion_is_rejected(
        self, settings: Settings, client: TestClient
    ) -> None:
        """A different algorithm, correctly signed, still fails the pin."""
        token = forge(settings, algorithm="HS512")

        assert client.get("/any", headers=auth(token)).status_code == 401

    def test_refresh_token_is_not_an_access_token(
        self, settings: Settings, client: TestClient, users: Users
    ) -> None:
        user = add_user(users)
        token = forge(settings, sub=str(user.id), typ=TokenType.REFRESH.value)

        assert client.get("/any", headers=auth(token)).status_code == 401

    @pytest.mark.parametrize(
        "claim", ["iss", "aud"], ids=["wrong-issuer", "wrong-audience"]
    )
    def test_wrong_issuer_or_audience(
        self, settings: Settings, client: TestClient, claim: str
    ) -> None:
        token = forge(settings, **{claim: "somebody-else"})

        assert client.get("/any", headers=auth(token)).status_code == 401

    def test_unknown_subject(self, settings: Settings, client: TestClient) -> None:
        """A perfectly valid token for an account that no longer exists."""
        token = forge(settings)

        assert client.get("/any", headers=auth(token)).status_code == 401

    def test_session_revoked_after_issue(
        self, settings: Settings, client: TestClient, users: Users
    ) -> None:
        """Bumping `session_valid_after` kills tokens already in the wild."""
        issued = datetime.now(UTC) - timedelta(minutes=5)
        user = add_user(users, session_valid_after=datetime.now(UTC))
        token = create_access_token(
            user.id, user.role, settings=settings, issued_at=issued
        )

        assert client.get("/any", headers=auth(token)).status_code == 401

    def test_token_issued_after_the_cutoff_still_works(
        self, settings: Settings, client: TestClient, users: Users
    ) -> None:
        user = add_user(
            users, session_valid_after=datetime.now(UTC) - timedelta(hours=1)
        )
        token = create_access_token(user.id, user.role, settings=settings)

        assert client.get("/any", headers=auth(token)).status_code == 200


# ---------------------------------------------------------------------------
# 403 -- authenticated, but not permitted
# ---------------------------------------------------------------------------


class TestAccountGates:
    @pytest.mark.parametrize(
        "status",
        [AccountStatus.SUSPENDED, AccountStatus.PENDING_VERIFICATION],
    )
    def test_inactive_account_is_forbidden_not_unauthenticated(
        self,
        settings: Settings,
        client: TestClient,
        users: Users,
        status: AccountStatus,
    ) -> None:
        """403, because refreshing the token would not help."""
        user = add_user(users, status=status)
        token = create_access_token(user.id, user.role, settings=settings)

        response = client.get("/any", headers=auth(token))

        assert response.status_code == 403
        assert error_code(response) == ErrorCode.FORBIDDEN


class TestRoleEnforcement:
    @pytest.mark.parametrize(
        ("role", "path"),
        [
            (Role.FOUNDER, "/founder-only"),
            (Role.INVESTOR, "/investor-only"),
            (Role.ADMIN, "/admin-only"),
        ],
    )
    def test_matching_role_is_allowed(
        self,
        settings: Settings,
        client: TestClient,
        users: Users,
        role: Role,
        path: str,
    ) -> None:
        user = add_user(users, role=role)
        token = create_access_token(user.id, user.role, settings=settings)

        response = client.get(path, headers=auth(token))

        assert response.status_code == 200
        assert response.json()["id"] == str(user.id)

    @pytest.mark.parametrize(
        ("role", "path"),
        [
            (Role.INVESTOR, "/founder-only"),
            (Role.FOUNDER, "/investor-only"),
            (Role.FOUNDER, "/admin-only"),
            (Role.INVESTOR, "/admin-only"),
        ],
    )
    def test_wrong_role_is_forbidden(
        self,
        settings: Settings,
        client: TestClient,
        users: Users,
        role: Role,
        path: str,
    ) -> None:
        user = add_user(users, role=role)
        token = create_access_token(user.id, user.role, settings=settings)

        response = client.get(path, headers=auth(token))

        assert response.status_code == 403
        assert error_code(response) == ErrorCode.FORBIDDEN

    def test_role_claim_in_the_token_is_not_trusted(
        self, settings: Settings, client: TestClient, users: Users
    ) -> None:
        """Privilege escalation: a founder mints a token claiming `admin`.

        The claim rides along for convenience, but the decision is made from
        the loaded record -- so this must be refused.
        """
        founder = add_user(users, role=Role.FOUNDER)
        token = forge(settings, sub=str(founder.id), role=Role.ADMIN.value)

        assert client.get("/admin-only", headers=auth(token)).status_code == 403
        assert client.get("/any", headers=auth(token)).json()["role"] == "founder"


# ---------------------------------------------------------------------------
# Non-disclosure
# ---------------------------------------------------------------------------


class TestNoLeakage:
    def test_token_never_appears_in_a_response(
        self, settings: Settings, client: TestClient
    ) -> None:
        token = forge(settings, key=OTHER_KEY)

        response = client.get("/any", headers=auth(token))

        assert token not in response.text
        assert "signature" not in response.text.lower()

    def test_token_never_appears_in_the_logs(
        self,
        settings: Settings,
        client: TestClient,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Rejections are logged with a reason, never the credential."""
        token = forge(settings, key=OTHER_KEY)

        with caplog.at_level(logging.INFO):
            client.get("/any", headers=auth(token))

        assert token not in caplog.text
        assert "access token rejected" in caplog.text

    def test_failure_reason_is_not_disclosed_to_the_caller(
        self, settings: Settings, client: TestClient, users: Users
    ) -> None:
        """Every 401 reads the same, so probing reveals nothing."""
        user = add_user(users)
        messages = {
            client.get("/any", headers=auth(token)).json()["error"]["message"]
            for token in (
                forge(settings, key=OTHER_KEY),
                forge(settings, iss="somebody-else"),
                forge(settings, sub=str(user.id), typ=TokenType.REFRESH.value),
                forge(settings),
            )
        }

        assert len(messages) == 1
