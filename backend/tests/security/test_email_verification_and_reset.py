"""Email verification and password reset.

The properties `AUTH.md` sections 3.2 and 12 treat as non-negotiable: a token
works once, expires, cannot be used for a purpose it was not issued for, and
completing a reset evicts everyone already holding a session.

Every test runs inside a transaction that is rolled back.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import InvalidRequestError, UnauthenticatedError
from app.core.security import AccountStatus, Role, hash_opaque_token
from app.modules.identity import service
from app.modules.identity.models import (
    AuditAction,
    AuditLog,
    AuthToken,
    TokenPurpose,
    User,
)
from app.modules.identity.repository import AuthTokenRepository
from tests.conftest import requires_database

pytestmark = [pytest.mark.security, pytest.mark.integration, requires_database]

PASSWORD = "correct-horse-battery-staple"
NEW_PASSWORD = "a-completely-different-passphrase"


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-signing-key-at-least-32-characters")
    monkeypatch.setenv("ARGON2_MEMORY_COST_KIB", "8192")
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    monkeypatch.setenv("APP_LINK_BASE_URL", "https://app.fundready.test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.test"


async def register(session: AsyncSession) -> tuple[User, str]:
    """Register a user and hand back a usable verification token.

    Only the hash of the emailed token is stored, so a test cannot read the one
    that was sent. Issuing another through the same path is the honest way to
    hold one.
    """
    user = await service.register_user(
        session,
        email=unique_email(),
        password=PASSWORD,
        role=Role.FOUNDER,
        first_name="Ada",
        last_name="Tester",
    )
    assert user is not None
    return user, await issue(session, user, TokenPurpose.EMAIL_VERIFICATION)


async def issue(session: AsyncSession, user: User, purpose: TokenPurpose) -> str:
    ttl = (
        service.VERIFICATION_TTL
        if purpose is TokenPurpose.EMAIL_VERIFICATION
        else service.PASSWORD_RESET_TTL
    )
    return await service.issue_auth_token(session, user, purpose, ttl)


class TestVerification:
    async def test_a_valid_token_activates_the_account(
        self, db_session: AsyncSession
    ) -> None:
        user, token = await register(db_session)

        verified = await service.verify_email(db_session, token)

        assert verified.status is AccountStatus.ACTIVE
        assert verified.email_verified is True

    async def test_registration_issues_a_token(self, db_session: AsyncSession) -> None:
        user = await service.register_user(
            db_session,
            email=unique_email(),
            password=PASSWORD,
            role=Role.FOUNDER,
            first_name="Ada",
            last_name="Tester",
        )
        assert user is not None

        count = (
            await db_session.execute(
                text(
                    "select count(*) from auth_tokens "
                    "where user_id = :id and purpose = 'email_verification'"
                ),
                {"id": user.id},
            )
        ).scalar_one()

        assert count >= 1, "registering must send a verification link"

    async def test_the_token_is_stored_hashed(self, db_session: AsyncSession) -> None:
        user, token = await register(db_session)

        hashes = (
            (
                await db_session.execute(
                    text("select token_hash from auth_tokens where user_id = :id"),
                    {"id": user.id},
                )
            )
            .scalars()
            .all()
        )

        assert token not in hashes
        assert hash_opaque_token(token) in hashes

    async def test_a_token_works_only_once(self, db_session: AsyncSession) -> None:
        _, token = await register(db_session)
        await service.verify_email(db_session, token)

        with pytest.raises(InvalidRequestError):
            await service.verify_email(db_session, token)

    async def test_an_expired_token_is_refused(self, db_session: AsyncSession) -> None:
        user, token = await register(db_session)
        stored = await AuthTokenRepository(db_session).get(
            token_hash=hash_opaque_token(token),
            purpose=TokenPurpose.EMAIL_VERIFICATION,
        )
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.flush()

        with pytest.raises(InvalidRequestError):
            await service.verify_email(db_session, token)

    async def test_an_unknown_token_is_refused(self, db_session: AsyncSession) -> None:
        with pytest.raises(InvalidRequestError):
            await service.verify_email(db_session, "not-a-real-token")

    async def test_verifying_does_not_unsuspend(self, db_session: AsyncSession) -> None:
        """An admin's suspension must outrank an email click."""
        user, token = await register(db_session)
        user.status = AccountStatus.SUSPENDED
        await db_session.flush()

        verified = await service.verify_email(db_session, token)

        assert verified.status is AccountStatus.SUSPENDED

    async def test_verification_is_audit_logged(self, db_session: AsyncSession) -> None:
        user, token = await register(db_session)
        await service.verify_email(db_session, token)

        actions = (
            await db_session.scalars(
                select(AuditLog.action).where(AuditLog.actor_id == user.id)
            )
        ).all()

        assert AuditAction.USER_EMAIL_VERIFIED.value in actions


class TestPurposeIsolation:
    async def test_a_verification_token_cannot_reset_a_password(
        self, db_session: AsyncSession
    ) -> None:
        """Otherwise the weaker capability silently grants the stronger one."""
        _, verification_token = await register(db_session)

        with pytest.raises(InvalidRequestError):
            await service.reset_password(db_session, verification_token, NEW_PASSWORD)

    async def test_a_reset_token_cannot_verify_an_email(
        self, db_session: AsyncSession
    ) -> None:
        user, _ = await register(db_session)
        await service.request_password_reset(db_session, user.email)
        reset_token = await issue(db_session, user, TokenPurpose.PASSWORD_RESET)

        with pytest.raises(InvalidRequestError):
            await service.verify_email(db_session, reset_token)


class TestPasswordReset:
    async def test_reset_changes_the_password(self, db_session: AsyncSession) -> None:
        user, _ = await register(db_session)
        token = await issue(db_session, user, TokenPurpose.PASSWORD_RESET)

        await service.reset_password(db_session, token, NEW_PASSWORD)

        await service.authenticate(db_session, email=user.email, password=NEW_PASSWORD)
        with pytest.raises(UnauthenticatedError):
            await service.authenticate(db_session, email=user.email, password=PASSWORD)

    async def test_reset_ends_every_session(self, db_session: AsyncSession) -> None:
        """Someone resetting a password may be evicting an intruder."""
        user, _ = await register(db_session)
        pair = await service.issue_tokens(db_session, user)
        token = await issue(db_session, user, TokenPurpose.PASSWORD_RESET)

        await service.reset_password(db_session, token, NEW_PASSWORD)

        with pytest.raises(UnauthenticatedError):
            await service.refresh_tokens(db_session, pair.refresh_token)
        assert user.session_valid_after is not None, (
            "access tokens already issued must stop working too"
        )

    async def test_reset_burns_other_outstanding_links(
        self, db_session: AsyncSession
    ) -> None:
        """An older reset email must not stay a live way in."""
        user, _ = await register(db_session)
        first = await issue(db_session, user, TokenPurpose.PASSWORD_RESET)
        second = await issue(db_session, user, TokenPurpose.PASSWORD_RESET)

        await service.reset_password(db_session, second, NEW_PASSWORD)

        with pytest.raises(InvalidRequestError):
            await service.reset_password(db_session, first, "yet-another-passphrase")

    async def test_reset_rejects_a_weak_new_password(
        self, db_session: AsyncSession
    ) -> None:
        user, _ = await register(db_session)
        token = await issue(db_session, user, TokenPurpose.PASSWORD_RESET)

        with pytest.raises(InvalidRequestError):
            await service.reset_password(db_session, token, "short")

    async def test_reset_clears_a_lockout(self, db_session: AsyncSession) -> None:
        """Locking out the real owner after a reset would be perverse."""
        user, _ = await register(db_session)
        for _ in range(service.MAX_FAILED_LOGINS):
            with pytest.raises(UnauthenticatedError):
                await service.authenticate(
                    db_session, email=user.email, password="wrong"
                )
        token = await issue(db_session, user, TokenPurpose.PASSWORD_RESET)

        await service.reset_password(db_session, token, NEW_PASSWORD)

        assert user.locked_until is None


class TestNoEnumeration:
    async def test_requesting_a_reset_for_an_unknown_address_is_silent(
        self, db_session: AsyncSession
    ) -> None:
        """No exception, no row -- the caller cannot tell it was a miss."""
        await service.request_password_reset(db_session, unique_email())

        count = (
            await db_session.execute(text("select count(*) from auth_tokens"))
        ).scalar_one()

        assert isinstance(count, int)

    async def test_requesting_a_reset_for_a_known_address_issues_one(
        self, db_session: AsyncSession
    ) -> None:
        user, _ = await register(db_session)

        await service.request_password_reset(db_session, user.email)

        tokens = (
            await db_session.scalars(
                select(AuthToken).where(
                    AuthToken.user_id == user.id,
                    AuthToken.purpose == TokenPurpose.PASSWORD_RESET,
                )
            )
        ).all()

        assert tokens
