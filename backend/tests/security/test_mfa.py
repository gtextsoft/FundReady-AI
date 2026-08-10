"""Two-factor authentication.

`AUTH.md` section 9 makes MFA mandatory for admins -- the role that can reveal
any full report -- so the properties tested here are: enrolment cannot be
completed without proving the authenticator holds the secret, the secret is
encrypted rather than stored plainly, a code cannot be replayed, and a recovery
code works exactly once.

That every admin *capability* also requires a second factor -- report reveal,
admin-tier report, benchmarks, task reopen, and user management -- is covered
in `tests/security/test_admin_mfa_required.py`. Enrolment alone does not prove
the capabilities honour it.
"""

import uuid
from collections.abc import Iterator

import pyotp
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ForbiddenError, InvalidRequestError, UnauthenticatedError
from app.core.security import (
    Role,
    TokenType,
    create_mfa_challenge_token,
    decode_access_token,
    decrypt_mfa_secret,
)
from app.modules.identity import service
from app.modules.identity.models import AuditAction, AuditLog, MfaRecoveryCode, User
from tests.conftest import requires_database

pytestmark = [pytest.mark.security, pytest.mark.integration, requires_database]

PASSWORD = "correct-horse-battery-staple"
MFA_KEY = "a-development-mfa-encryption-key-32ch"


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-signing-key-at-least-32-characters")
    monkeypatch.setenv("MFA_SECRET_ENCRYPTION_KEY", MFA_KEY)
    monkeypatch.setenv("ARGON2_MEMORY_COST_KIB", "8192")
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.test"


async def make_user(session: AsyncSession, role: Role = Role.FOUNDER) -> User:
    user = await service.register_user(
        session,
        email=unique_email(),
        password=PASSWORD,
        role=role,
        first_name="Ada",
        last_name="Tester",
    )
    assert user is not None
    user.role = role
    await session.flush()
    return user


def code_for(secret: str) -> str:
    return str(pyotp.TOTP(secret, digits=6, interval=30).now())


async def enrol(session: AsyncSession, user: User) -> tuple[str, list[str]]:
    """Enrol fully and return the secret plus the recovery codes."""
    enrolment = await service.start_mfa_enrolment(session, user)
    codes = await service.confirm_mfa_enrolment(
        session, user, code_for(enrolment.secret)
    )
    return enrolment.secret, codes


class TestEnrolment:
    async def test_starting_does_not_enable(self, db_session: AsyncSession) -> None:
        """A mistyped setup must not lock the user out of their own account."""
        user = await make_user(db_session)

        await service.start_mfa_enrolment(db_session, user)

        assert user.mfa_enabled is False
        assert user.mfa_secret_encrypted is not None

    async def test_confirming_with_a_valid_code_enables(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)
        enrolment = await service.start_mfa_enrolment(db_session, user)

        codes = await service.confirm_mfa_enrolment(
            db_session, user, code_for(enrolment.secret)
        )

        assert user.mfa_enabled is True
        assert len(codes) == service.RECOVERY_CODE_COUNT

    async def test_confirming_with_a_wrong_code_does_not_enable(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)
        await service.start_mfa_enrolment(db_session, user)

        with pytest.raises(InvalidRequestError):
            await service.confirm_mfa_enrolment(db_session, user, "000000")

        assert user.mfa_enabled is False

    async def test_confirming_without_starting_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)

        with pytest.raises(InvalidRequestError):
            await service.confirm_mfa_enrolment(db_session, user, "123456")

    async def test_the_secret_is_encrypted_at_rest(
        self, db_session: AsyncSession
    ) -> None:
        """A database leak alone must not hand over second factors."""
        user = await make_user(db_session)
        secret, _ = await enrol(db_session, user)

        stored = (
            await db_session.execute(
                text("select mfa_secret_encrypted from users where id = :id"),
                {"id": user.id},
            )
        ).scalar_one()

        assert secret not in stored
        assert decrypt_mfa_secret(stored) == secret

    async def test_enabling_is_audit_logged(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session)
        await enrol(db_session, user)

        actions = (
            await db_session.scalars(
                select(AuditLog.action).where(AuditLog.actor_id == user.id)
            )
        ).all()

        assert AuditAction.USER_MFA_ENABLED.value in actions

    async def test_re_enrolling_replaces_the_old_recovery_codes(
        self, db_session: AsyncSession
    ) -> None:
        """The previous device's codes must not survive."""
        user = await make_user(db_session)
        _, first_codes = await enrol(db_session, user)
        user.mfa_last_used_step = None
        _, second_codes = await enrol(db_session, user)

        assert set(first_codes).isdisjoint(second_codes)
        stored = (
            await db_session.scalars(
                select(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id)
            )
        ).all()
        assert len(stored) == service.RECOVERY_CODE_COUNT


class TestLoginChallenge:
    async def test_login_reports_mfa_when_enabled(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)
        await enrol(db_session, user)

        authenticated = await service.authenticate(
            db_session, email=user.email, password=PASSWORD
        )

        assert authenticated.mfa_enabled is True, (
            "the router branches on this to withhold tokens"
        )

    async def test_the_challenge_token_is_not_an_access_token(
        self, db_session: AsyncSession
    ) -> None:
        """Otherwise passing the password alone would grant access."""
        user = await make_user(db_session)
        challenge = create_mfa_challenge_token(user.id)

        with pytest.raises(UnauthenticatedError):
            decode_access_token(challenge)

    async def test_a_valid_code_completes_the_login(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)
        secret, _ = await enrol(db_session, user)
        user.mfa_last_used_step = None
        challenge = create_mfa_challenge_token(user.id)

        pair = await service.verify_mfa_challenge(
            db_session, challenge, code_for(secret)
        )

        assert decode_access_token(pair.access_token).subject == user.id

    async def test_a_wrong_code_is_refused(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session)
        await enrol(db_session, user)
        challenge = create_mfa_challenge_token(user.id)

        with pytest.raises(UnauthenticatedError):
            await service.verify_mfa_challenge(db_session, challenge, "000000")

    async def test_a_code_cannot_be_replayed(self, db_session: AsyncSession) -> None:
        """An intercepted code is useless even inside its own 30-second step."""
        user = await make_user(db_session)
        secret, _ = await enrol(db_session, user)
        user.mfa_last_used_step = None
        code = code_for(secret)
        await service.verify_mfa_challenge(
            db_session, create_mfa_challenge_token(user.id), code
        )

        with pytest.raises(UnauthenticatedError):
            await service.verify_mfa_challenge(
                db_session, create_mfa_challenge_token(user.id), code
            )

    async def test_an_access_token_is_not_a_challenge_token(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)
        secret, _ = await enrol(db_session, user)
        user.mfa_last_used_step = None
        pair = await service.issue_tokens(db_session, user)

        with pytest.raises(UnauthenticatedError):
            await service.verify_mfa_challenge(
                db_session, pair.access_token, code_for(secret)
            )

    async def test_a_suspended_account_cannot_complete_mfa(
        self, db_session: AsyncSession
    ) -> None:
        from app.core.security import AccountStatus

        user = await make_user(db_session)
        secret, _ = await enrol(db_session, user)
        user.mfa_last_used_step = None
        user.status = AccountStatus.SUSPENDED
        await db_session.flush()

        with pytest.raises(ForbiddenError):
            await service.verify_mfa_challenge(
                db_session, create_mfa_challenge_token(user.id), code_for(secret)
            )


class TestRecoveryCodes:
    async def test_a_recovery_code_completes_the_login(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)
        _, codes = await enrol(db_session, user)

        pair = await service.verify_mfa_challenge(
            db_session, create_mfa_challenge_token(user.id), codes[0]
        )

        assert decode_access_token(pair.access_token).subject == user.id

    async def test_a_recovery_code_works_only_once(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)
        _, codes = await enrol(db_session, user)
        await service.verify_mfa_challenge(
            db_session, create_mfa_challenge_token(user.id), codes[0]
        )

        with pytest.raises(UnauthenticatedError):
            await service.verify_mfa_challenge(
                db_session, create_mfa_challenge_token(user.id), codes[0]
            )

    async def test_other_recovery_codes_still_work(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)
        _, codes = await enrol(db_session, user)
        await service.verify_mfa_challenge(
            db_session, create_mfa_challenge_token(user.id), codes[0]
        )

        pair = await service.verify_mfa_challenge(
            db_session, create_mfa_challenge_token(user.id), codes[1]
        )

        assert pair.access_token

    async def test_recovery_codes_are_stored_hashed(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)
        _, codes = await enrol(db_session, user)

        stored = (
            (
                await db_session.execute(
                    text(
                        "select code_hash from mfa_recovery_codes where user_id = :id"
                    ),
                    {"id": user.id},
                )
            )
            .scalars()
            .all()
        )

        for code in codes:
            assert code not in stored
        assert all(value.startswith("$argon2id$") for value in stored)

    async def test_using_one_is_audit_logged(self, db_session: AsyncSession) -> None:
        """A spent recovery code is a signal worth keeping."""
        user = await make_user(db_session)
        _, codes = await enrol(db_session, user)
        await service.verify_mfa_challenge(
            db_session, create_mfa_challenge_token(user.id), codes[0]
        )

        actions = (
            await db_session.scalars(
                select(AuditLog.action).where(AuditLog.actor_id == user.id)
            )
        ).all()

        assert AuditAction.USER_MFA_RECOVERY_CODE_USED.value in actions


def test_the_challenge_token_type_is_distinct() -> None:
    """Three token types, none interchangeable."""
    assert len({TokenType.ACCESS, TokenType.REFRESH, TokenType.MFA_CHALLENGE}) == 3
