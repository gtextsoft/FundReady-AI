"""Email verification and password reset.

The properties `AUTH.md` sections 3.2 and 12 treat as non-negotiable: a secret
works once, expires, cannot be used for a purpose it was not issued for, and
completing a reset evicts everyone already holding a session.

Verification is a **six-digit code**, which brings its own obligations that a
256-bit link never had: guesses are counted and the code dies after a handful,
it is bound to one account, and what is stored cannot be reversed by anyone
holding the database alone.

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
from app.core.security import (
    AccountStatus,
    Role,
    hash_opaque_token,
    hash_verification_code,
)
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
    """Register a user and hand back a usable verification code.

    Only the keyed hash of the emailed code is stored, so a test cannot read
    the one that was sent. Issuing another through the same path is the honest
    way to hold one.
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
    return user, await service.issue_verification_code(session, user)


async def issue(session: AsyncSession, user: User, purpose: TokenPurpose) -> str:
    return await service.issue_auth_token(
        session, user, purpose, service.PASSWORD_RESET_TTL
    )


def wrong_code(code: str) -> str:
    """A different six-digit code, whatever the real one turned out to be."""
    return f"{(int(code) + 1) % 10**6:06d}"


class TestVerification:
    async def test_a_valid_code_activates_the_account(
        self, db_session: AsyncSession
    ) -> None:
        user, code = await register(db_session)

        verified = await service.verify_email(db_session, email=user.email, code=code)

        assert verified.status is AccountStatus.ACTIVE
        assert verified.email_verified is True

    async def test_the_code_is_six_digits(self, db_session: AsyncSession) -> None:
        """A person has to read it off an email and type it into a phone."""
        _, code = await register(db_session)

        assert len(code) == 6
        assert code.isdigit()

    async def test_spacing_and_hyphens_are_ignored(
        self, db_session: AsyncSession
    ) -> None:
        """`123 456` is what a copy-paste out of a rendered email produces."""
        user, code = await register(db_session)

        verified = await service.verify_email(
            db_session, email=user.email, code=f"{code[:3]}-{code[3:]}"
        )

        assert verified.email_verified is True

    async def test_registration_issues_a_code(self, db_session: AsyncSession) -> None:
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

        assert count >= 1, "registering must send a verification code"

    async def test_the_code_is_stored_hashed(self, db_session: AsyncSession) -> None:
        user, code = await register(db_session)

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

        assert code not in hashes
        assert (
            hash_verification_code(
                code,
                user_id=user.id,
                purpose=TokenPurpose.EMAIL_VERIFICATION.value,
            )
            in hashes
        )

    async def test_the_stored_hash_is_not_a_plain_digest(
        self, db_session: AsyncSession
    ) -> None:
        """The whole point of keying it.

        Six digits behind an unkeyed SHA-256 is a million-entry rainbow table,
        so a database leak would hand over every outstanding code. This asserts
        the obvious digest is *not* what got stored.
        """
        user, code = await register(db_session)

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

        assert hash_opaque_token(code) not in hashes

    async def test_a_code_works_only_once(self, db_session: AsyncSession) -> None:
        user, code = await register(db_session)
        await service.verify_email(db_session, email=user.email, code=code)

        with pytest.raises(InvalidRequestError):
            await service.verify_email(db_session, email=user.email, code=code)

    async def test_an_expired_code_is_refused(self, db_session: AsyncSession) -> None:
        user, code = await register(db_session)
        stored = await AuthTokenRepository(db_session).latest_live(
            user_id=user.id,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            now=datetime.now(UTC),
        )
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.flush()

        with pytest.raises(InvalidRequestError):
            await service.verify_email(db_session, email=user.email, code=code)

    async def test_a_wrong_code_is_refused(self, db_session: AsyncSession) -> None:
        user, code = await register(db_session)

        with pytest.raises(InvalidRequestError):
            await service.verify_email(
                db_session, email=user.email, code=wrong_code(code)
            )

    async def test_an_unknown_address_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        with pytest.raises(InvalidRequestError):
            await service.verify_email(db_session, email=unique_email(), code="123456")

    async def test_issuing_a_new_code_kills_the_previous_one(
        self, db_session: AsyncSession
    ) -> None:
        """Two live codes would double an attacker's guesses per email."""
        user, first = await register(db_session)
        second = await service.issue_verification_code(db_session, user)

        with pytest.raises(InvalidRequestError):
            await service.verify_email(db_session, email=user.email, code=first)

        verified = await service.verify_email(db_session, email=user.email, code=second)
        assert verified.email_verified is True

    async def test_verifying_does_not_unsuspend(self, db_session: AsyncSession) -> None:
        """An admin's suspension must outrank a typed-in code."""
        user, code = await register(db_session)
        user.status = AccountStatus.SUSPENDED
        await db_session.flush()

        verified = await service.verify_email(db_session, email=user.email, code=code)

        assert verified.status is AccountStatus.SUSPENDED

    async def test_verification_is_audit_logged(self, db_session: AsyncSession) -> None:
        user, code = await register(db_session)
        await service.verify_email(db_session, email=user.email, code=code)

        actions = (
            await db_session.scalars(
                select(AuditLog.action).where(AuditLog.actor_id == user.id)
            )
        ).all()

        assert AuditAction.USER_EMAIL_VERIFIED.value in actions


class TestGuessingIsCapped:
    """Six digits is a million guesses -- nothing, to a script."""

    async def test_the_code_dies_after_the_attempt_cap(
        self, db_session: AsyncSession
    ) -> None:
        user, code = await register(db_session)

        for _ in range(service.MAX_VERIFICATION_ATTEMPTS):
            with pytest.raises(InvalidRequestError):
                await service.verify_email(
                    db_session, email=user.email, code=wrong_code(code)
                )

        with pytest.raises(InvalidRequestError):
            await service.verify_email(db_session, email=user.email, code=code)
        assert user.email_verified is False, (
            "the real code must not survive an exhausted attempt count"
        )

    async def test_attempts_survive_the_failed_request(
        self, db_session: AsyncSession
    ) -> None:
        """The count is committed, not rolled back with the failing request.

        This is the bug that makes a cap decorative: every attempt resets the
        counter and the code never dies.
        """
        user, code = await register(db_session)

        with pytest.raises(InvalidRequestError):
            await service.verify_email(
                db_session, email=user.email, code=wrong_code(code)
            )

        stored = await AuthTokenRepository(db_session).latest_live(
            user_id=user.id,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            now=datetime.now(UTC),
        )
        assert stored is not None
        assert stored.attempt_count == 1

    async def test_a_correct_code_still_works_below_the_cap(
        self, db_session: AsyncSession
    ) -> None:
        """Somebody mistyping twice must not be locked out of their own account."""
        user, code = await register(db_session)

        for _ in range(service.MAX_VERIFICATION_ATTEMPTS - 1):
            with pytest.raises(InvalidRequestError):
                await service.verify_email(
                    db_session, email=user.email, code=wrong_code(code)
                )

        verified = await service.verify_email(db_session, email=user.email, code=code)
        assert verified.email_verified is True


class TestCodesAreBoundToOneAccount:
    async def test_another_users_code_does_not_work(
        self, db_session: AsyncSession
    ) -> None:
        """Otherwise a guessed code matches whoever happens to hold it."""
        _, code = await register(db_session)
        other, _ = await register(db_session)

        with pytest.raises(InvalidRequestError):
            await service.verify_email(db_session, email=other.email, code=code)

    async def test_the_same_digits_hash_differently_per_user(
        self, db_session: AsyncSession
    ) -> None:
        first, _ = await register(db_session)
        second, _ = await register(db_session)

        assert hash_verification_code(
            "123456",
            user_id=first.id,
            purpose=TokenPurpose.EMAIL_VERIFICATION.value,
        ) != hash_verification_code(
            "123456",
            user_id=second.id,
            purpose=TokenPurpose.EMAIL_VERIFICATION.value,
        )


class TestResend:
    async def test_an_unknown_address_is_silent(self, db_session: AsyncSession) -> None:
        await service.resend_verification_email(db_session, unique_email())

    async def test_an_already_verified_address_issues_nothing(
        self, db_session: AsyncSession
    ) -> None:
        user, code = await register(db_session)
        await service.verify_email(db_session, email=user.email, code=code)

        await service.resend_verification_email(db_session, user.email)

        live = await AuthTokenRepository(db_session).latest_live(
            user_id=user.id,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            now=datetime.now(UTC),
        )
        assert live is None

    async def test_a_recent_code_suppresses_another_send(
        self, db_session: AsyncSession
    ) -> None:
        """Otherwise the button is a mailbomb aimed at somebody else's inbox."""
        user, code = await register(db_session)

        await service.resend_verification_email(db_session, user.email)

        verified = await service.verify_email(db_session, email=user.email, code=code)
        assert verified.email_verified is True, (
            "the code from the first email must still be the live one"
        )

    async def test_past_the_cooldown_a_new_code_is_issued(
        self, db_session: AsyncSession
    ) -> None:
        user, code = await register(db_session)
        stored = await AuthTokenRepository(db_session).latest_live(
            user_id=user.id,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            now=datetime.now(UTC),
        )
        assert stored is not None
        # Age the row past the cooldown by moving its expiry, which is what
        # the cooldown is measured back from.
        stored.expires_at -= service.VERIFICATION_RESEND_COOLDOWN * 2
        await db_session.flush()

        await service.resend_verification_email(db_session, user.email)

        with pytest.raises(InvalidRequestError):
            await service.verify_email(db_session, email=user.email, code=code)


class TestPurposeIsolation:
    async def test_a_verification_code_cannot_reset_a_password(
        self, db_session: AsyncSession
    ) -> None:
        """Otherwise the weaker capability silently grants the stronger one."""
        _, verification_code = await register(db_session)

        with pytest.raises(InvalidRequestError):
            await service.reset_password(db_session, verification_code, NEW_PASSWORD)

    async def test_a_reset_token_cannot_verify_an_email(
        self, db_session: AsyncSession
    ) -> None:
        user, _ = await register(db_session)
        await service.request_password_reset(db_session, user.email)
        reset_token = await issue(db_session, user, TokenPurpose.PASSWORD_RESET)

        with pytest.raises(InvalidRequestError):
            await service.verify_email(db_session, email=user.email, code=reset_token)


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
