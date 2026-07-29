"""Registration, login, and refresh-token rotation, against a real database.

The properties asserted here are the ones `AUTH.md` treats as non-negotiable:

* a password is never stored in plaintext, returned, or logged
* registration and login never reveal whether an account exists
* nobody can make themselves an admin
* a refresh token works exactly once, and replaying one ends the whole session

Every test runs inside a transaction that is rolled back, so nothing survives.
"""

import logging
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ForbiddenError, InvalidRequestError, UnauthenticatedError
from app.core.security import (
    AccountStatus,
    Role,
    decode_access_token,
    hash_refresh_token,
)
from app.modules.identity import service
from app.modules.identity.models import AuditAction, AuditLog, RefreshToken, User
from tests.conftest import requires_database

pytestmark = [pytest.mark.security, pytest.mark.integration, requires_database]

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A signing key, and Argon2 cheap enough to run hundreds of times.

    Production floors are enforced by `validate_settings` and covered in
    `tests/unit/test_config.py`; paying 64 MiB per hash here would make the
    suite unusable without testing anything extra.
    """
    monkeypatch.setenv("JWT_SECRET_KEY", "test-signing-key-at-least-32-characters")
    monkeypatch.setenv("ARGON2_MEMORY_COST_KIB", "8192")
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.test"


async def make_user(
    session: AsyncSession,
    *,
    role: Role = Role.FOUNDER,
    status: AccountStatus = AccountStatus.ACTIVE,
    password: str = PASSWORD,
) -> User:
    user = await service.register_user(
        session, email=unique_email(), password=password, role=role
    )
    assert user is not None
    user.status = status
    await session.flush()
    return user


class TestRegistration:
    async def test_creates_a_pending_user(self, db_session: AsyncSession) -> None:
        user = await service.register_user(
            db_session, email=unique_email(), password=PASSWORD, role=Role.FOUNDER
        )

        assert user is not None
        assert user.status is AccountStatus.PENDING_VERIFICATION
        assert user.role is Role.FOUNDER
        assert user.email_verified is False

    async def test_password_is_never_stored_in_plaintext(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)

        stored = (
            await db_session.execute(
                text("select password_hash from users where id = :id"), {"id": user.id}
            )
        ).scalar_one()

        assert PASSWORD not in stored
        assert stored.startswith("$argon2id$"), "must be Argon2id, not a fast hash"

    async def test_email_is_normalised(self, db_session: AsyncSession) -> None:
        """Otherwise `A@x.test` and `a@x.test` become two accounts."""
        email = unique_email()
        user = await service.register_user(
            db_session,
            email=f"  {email.upper()}  ",
            password=PASSWORD,
            role=Role.FOUNDER,
        )

        assert user is not None
        assert user.email == email

    async def test_duplicate_registration_is_indistinguishable(
        self, db_session: AsyncSession
    ) -> None:
        """The endpoint must not become an account-existence oracle."""
        email = unique_email()
        first = await service.register_user(
            db_session, email=email, password=PASSWORD, role=Role.FOUNDER
        )
        second = await service.register_user(
            db_session, email=email, password=PASSWORD, role=Role.FOUNDER
        )

        assert first is not None
        assert second is None, "no second account, and the caller cannot tell"

        count = (
            await db_session.execute(
                text("select count(*) from users where email = :e"), {"e": email}
            )
        ).scalar_one()
        assert count == 1

    async def test_nobody_can_self_register_as_admin(
        self, db_session: AsyncSession
    ) -> None:
        """Privilege escalation at the front door."""
        with pytest.raises(ForbiddenError):
            await service.register_user(
                db_session, email=unique_email(), password=PASSWORD, role=Role.ADMIN
            )

    @pytest.mark.parametrize(
        "password",
        ["short", "aaaaaaaaaaa", "fundready-platform-2026"],
        ids=["too-short", "eleven-chars", "contains-product-name"],
    )
    async def test_weak_passwords_are_rejected(
        self, db_session: AsyncSession, password: str
    ) -> None:
        with pytest.raises(InvalidRequestError):
            await service.register_user(
                db_session, email=unique_email(), password=password, role=Role.FOUNDER
            )

    async def test_password_may_not_contain_the_email(
        self, db_session: AsyncSession
    ) -> None:
        email = "jonathan@example.test"
        with pytest.raises(InvalidRequestError):
            await service.register_user(
                db_session, email=email, password="jonathan-password", role=Role.FOUNDER
            )

    async def test_registration_is_audit_logged(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session)

        actions = (
            await db_session.scalars(
                select(AuditLog.action).where(AuditLog.actor_id == user.id)
            )
        ).all()

        assert AuditAction.USER_REGISTERED.value in actions


class TestLogin:
    async def test_correct_credentials_succeed(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session)

        authenticated = await service.authenticate(
            db_session, email=user.email, password=PASSWORD
        )

        assert authenticated.id == user.id
        assert authenticated.last_login_at is not None

    async def test_unknown_email_and_wrong_password_are_indistinguishable(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)

        with pytest.raises(UnauthenticatedError) as wrong_password:
            await service.authenticate(
                db_session, email=user.email, password="not-the-password"
            )
        with pytest.raises(UnauthenticatedError) as unknown_email:
            await service.authenticate(
                db_session, email=unique_email(), password=PASSWORD
            )

        assert wrong_password.value.message == unknown_email.value.message

    async def test_suspended_account_cannot_log_in(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session, status=AccountStatus.SUSPENDED)

        with pytest.raises(ForbiddenError):
            await service.authenticate(db_session, email=user.email, password=PASSWORD)

    async def test_unverified_account_may_log_in(
        self, db_session: AsyncSession
    ) -> None:
        """Login works; protected endpoints still refuse until verification."""
        user = await make_user(db_session, status=AccountStatus.PENDING_VERIFICATION)

        authenticated = await service.authenticate(
            db_session, email=user.email, password=PASSWORD
        )

        assert authenticated.status is AccountStatus.PENDING_VERIFICATION

    async def test_repeated_failures_lock_the_account(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)

        for _ in range(service.MAX_FAILED_LOGINS):
            with pytest.raises(UnauthenticatedError):
                await service.authenticate(
                    db_session, email=user.email, password="wrong"
                )

        assert user.locked_until is not None
        # Even the *correct* password is refused while locked.
        with pytest.raises(UnauthenticatedError):
            await service.authenticate(db_session, email=user.email, password=PASSWORD)

    async def test_the_failure_count_survives_the_failing_request(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: same shape as the reuse bug.

        A failed login increments the counter and then raises. If that increment
        rode on the request's transaction it would be rolled back with the
        failure, the counter would reset every attempt, and lockout would never
        fire -- a defence that looks present and does nothing.
        """
        user = await make_user(db_session)
        commits: list[int] = []
        original = db_session.commit

        async def counting_commit() -> None:
            commits.append(1)
            await original()

        monkeypatch.setattr(db_session, "commit", counting_commit)

        with pytest.raises(UnauthenticatedError):
            await service.authenticate(db_session, email=user.email, password="wrong")

        assert commits, "the failure count must be committed, not left to the request"

    async def test_a_successful_login_clears_the_counter(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)
        with pytest.raises(UnauthenticatedError):
            await service.authenticate(db_session, email=user.email, password="wrong")

        await service.authenticate(db_session, email=user.email, password=PASSWORD)

        assert user.failed_login_count == 0

    async def test_the_password_never_reaches_the_logs(
        self, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
    ) -> None:
        user = await make_user(db_session)

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(UnauthenticatedError):
                await service.authenticate(
                    db_session, email=user.email, password=PASSWORD + "x"
                )
            await service.authenticate(db_session, email=user.email, password=PASSWORD)

        assert PASSWORD not in caplog.text


class TestRefreshRotation:
    async def test_login_issues_a_usable_pair(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session)

        pair = await service.issue_tokens(db_session, user)

        claims = decode_access_token(pair.access_token)
        assert claims.subject == user.id
        assert pair.expires_in > 0

    async def test_the_raw_refresh_token_is_not_stored(
        self, db_session: AsyncSession
    ) -> None:
        """A database leak must not hand over working sessions."""
        user = await make_user(db_session)
        pair = await service.issue_tokens(db_session, user)

        rows = (
            (
                await db_session.execute(
                    text("select token_hash from refresh_tokens where user_id = :id"),
                    {"id": user.id},
                )
            )
            .scalars()
            .all()
        )

        assert pair.refresh_token not in rows
        assert hash_refresh_token(pair.refresh_token) in rows

    async def test_rotation_invalidates_the_previous_token(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)
        first = await service.issue_tokens(db_session, user)

        second = await service.refresh_tokens(db_session, first.refresh_token)

        assert second.refresh_token != first.refresh_token
        # The new one works.
        await service.refresh_tokens(db_session, second.refresh_token)

    async def test_replaying_a_used_token_kills_the_whole_family(
        self, db_session: AsyncSession
    ) -> None:
        """The control that limits a stolen refresh token to a single use."""
        user = await make_user(db_session)
        first = await service.issue_tokens(db_session, user)
        second = await service.refresh_tokens(db_session, first.refresh_token)

        # The thief (or the victim) replays the spent token.
        with pytest.raises(UnauthenticatedError):
            await service.refresh_tokens(db_session, first.refresh_token)

        # The successor is now dead too -- the entire session is gone.
        with pytest.raises(UnauthenticatedError):
            await service.refresh_tokens(db_session, second.refresh_token)

    async def test_reuse_revokes_access_tokens_as_well(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)
        first = await service.issue_tokens(db_session, user)
        await service.refresh_tokens(db_session, first.refresh_token)

        with pytest.raises(UnauthenticatedError):
            await service.refresh_tokens(db_session, first.refresh_token)

        assert user.session_valid_after is not None, (
            "bumping this is what invalidates access tokens already issued"
        )

    async def test_reuse_is_audit_logged(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session)
        first = await service.issue_tokens(db_session, user)
        await service.refresh_tokens(db_session, first.refresh_token)
        with pytest.raises(UnauthenticatedError):
            await service.refresh_tokens(db_session, first.refresh_token)

        actions = (
            await db_session.scalars(
                select(AuditLog.action).where(AuditLog.actor_id == user.id)
            )
        ).all()

        assert AuditAction.REFRESH_TOKEN_REUSE_DETECTED.value in actions

    async def test_the_revocation_survives_the_failing_request(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: reuse detection revokes, then raises.

        The raise makes the request fail, and a failed request rolls its
        transaction back -- which would undo the revocation and leave the
        stolen family alive while the client saw a 401. The revocation has to
        be committed before the exception escapes.
        """
        user = await make_user(db_session)
        first = await service.issue_tokens(db_session, user)
        await service.refresh_tokens(db_session, first.refresh_token)

        commits: list[int] = []
        original = db_session.commit

        async def counting_commit() -> None:
            commits.append(1)
            await original()

        monkeypatch.setattr(db_session, "commit", counting_commit)

        with pytest.raises(UnauthenticatedError):
            await service.refresh_tokens(db_session, first.refresh_token)

        assert commits, "the revocation must be committed, not left to the request"

    async def test_an_unknown_token_is_refused(self, db_session: AsyncSession) -> None:
        with pytest.raises(UnauthenticatedError):
            await service.refresh_tokens(db_session, "not-a-real-token")

    async def test_rotation_keeps_the_family(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session)
        first = await service.issue_tokens(db_session, user)
        second = await service.refresh_tokens(db_session, first.refresh_token)

        families = set(
            (
                await db_session.scalars(
                    select(RefreshToken.family_id).where(
                        RefreshToken.user_id == user.id
                    )
                )
            ).all()
        )

        assert len(families) == 1, "a rotation continues the session, not starts one"
        assert second.refresh_token != first.refresh_token


class TestLogout:
    async def test_logout_revokes_the_family(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session)
        pair = await service.issue_tokens(db_session, user)

        await service.logout(db_session, pair.refresh_token)

        with pytest.raises(UnauthenticatedError):
            await service.refresh_tokens(db_session, pair.refresh_token)

    async def test_logout_is_silent_for_an_unknown_token(
        self, db_session: AsyncSession
    ) -> None:
        """It must not reveal whether the token was ever real."""
        await service.logout(db_session, "never-issued")


class TestUserLoader:
    async def test_resolves_the_authoritative_record(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session, role=Role.INVESTOR)

        loaded = await service.load_current_user(db_session, user.id)

        assert loaded is not None
        assert loaded.role is Role.INVESTOR
        assert loaded.status is AccountStatus.ACTIVE

    async def test_unknown_user_resolves_to_nothing(
        self, db_session: AsyncSession
    ) -> None:
        assert await service.load_current_user(db_session, uuid.uuid4()) is None
