"""Identity business logic.

Layer: **service** (ARCHITECTURE.md section 3) -- business logic and
orchestration. Performs authorization and ownership checks (AUTH.md sections
5-6), calls this module's `repository`, `app.ai`, and other modules' public
service functions only (never their internals). Enqueues background jobs.
Selects the tier serializer for every response carrying report data
(DECISIONS.md D8).

`record_action` is this module's public entry point for the audit log. Other
modules call it -- brokerage when a full report is revealed, commerce on a
purchase, and so on -- rather than reaching for the repository themselves.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import (
    ForbiddenError,
    InvalidRequestError,
    UnauthenticatedError,
)
from app.core.logging import get_request_id
from app.core.security import (
    AccountStatus,
    CurrentUser,
    Role,
    create_access_token,
    generate_opaque_token,
    generate_refresh_token,
    hash_opaque_token,
    hash_password,
    hash_refresh_token,
    verify_dummy_password,
    verify_password,
)
from app.modules.identity.models import (
    AuditAction,
    AuditLog,
    AuthToken,
    RefreshToken,
    TokenPurpose,
    User,
)
from app.modules.identity.repository import (
    AuditLogRepository,
    AuthTokenRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.modules.notifications import service as notifications

logger = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH: Final = 12
MAX_FAILED_LOGINS: Final = 10
LOCKOUT_DURATION: Final = timedelta(minutes=15)

# Roles a person may give themselves. Admin is provisioned by an existing admin
# and never through this path (AUTH.md section 3.2; the flow lands in T1.2d).
SELF_SERVICE_ROLES: Final = frozenset({Role.FOUNDER, Role.INVESTOR})


async def record_action(
    session: AsyncSession,
    action: AuditAction,
    *,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Append one entry to the immutable audit log.

    The current request id is attached automatically, so an audit row and the
    log lines from the same request can be tied together later without anyone
    remembering to pass it.

    Callers must not put secrets, tokens, or document contents in `details` --
    the audit log is retained indefinitely and cannot be edited afterwards
    (CLAUDE.md section 4).
    """
    payload = dict(details or {})

    request_id = get_request_id()
    if request_id is not None:
        payload.setdefault("request_id", request_id)

    return await AuditLogRepository(session).append(
        action=action.value,
        actor_id=actor_id,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=payload,
    )


# ---------------------------------------------------------------------------
# Registration and login (AUTH.md section 3)
# ---------------------------------------------------------------------------


def normalise_email(email: str) -> str:
    """Fold to one canonical form, so the unique index really prevents duplicates."""
    return email.strip().lower()


def validate_password(password: str, email: str) -> None:
    """Reject the obviously weak (AUTH.md section 12).

    Length beats composition rules, so there are no forced symbol classes. The
    breached-password check belongs with the rest of the rate limiting in T5.5.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidRequestError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )
    local_part = normalise_email(email).split("@", 1)[0]
    lowered = password.lower()
    if local_part and local_part in lowered:
        raise InvalidRequestError("Password must not contain your email address.")
    if "fundready" in lowered:
        raise InvalidRequestError("Password is too easy to guess.")


async def register_user(
    session: AsyncSession, *, email: str, password: str, role: Role
) -> User | None:
    """Register a founder or investor.

    Returns the new user, or **None when the email is already registered** --
    and the caller must respond identically either way. `AUTH.md` section 3.2
    requires it: any difference here turns registration into an
    account-existence oracle. Telling the real owner that someone tried is the
    job of the email, which arrives with T1.2a.
    """
    if role not in SELF_SERVICE_ROLES:
        # The message does not name the admin role: that would advertise its
        # existence to anyone poking at the endpoint.
        raise ForbiddenError("That account type cannot be created here.")

    normalised = normalise_email(email)
    validate_password(password, normalised)

    users = UserRepository(session)
    if await users.get_by_email(normalised) is not None:
        return None

    user = await users.create(
        email=normalised,
        password_hash=hash_password(password),
        role=role,
        status=AccountStatus.PENDING_VERIFICATION,
    )
    await record_action(
        session,
        AuditAction.USER_REGISTERED,
        actor_id=user.id,
        target_type="user",
        target_id=user.id,
        details={"role": role.value},
    )
    # Only for a genuinely new account. Sending on a duplicate would tell the
    # caller the address exists, which is precisely what returning None avoids.
    await send_verification_email(session, user)
    return user


def _invalid_credentials(reason: str) -> UnauthenticatedError:
    logger.info("login failed", extra={"context": {"reason": reason}})
    return UnauthenticatedError("Email or password is incorrect.")


async def _register_failed_login(
    session: AsyncSession, user: User, now: datetime
) -> None:
    user.failed_login_count += 1
    if user.failed_login_count >= MAX_FAILED_LOGINS:
        user.locked_until = now + LOCKOUT_DURATION
        user.failed_login_count = 0
    await record_action(
        session,
        AuditAction.USER_LOGIN_FAILED,
        actor_id=user.id,
        target_type="user",
        target_id=user.id,
        details={"locked": user.locked_until is not None},
    )
    # Committed here, not left to the request: the caller raises immediately
    # after this, and a failed request rolls its transaction back. Without the
    # commit the counter would reset on every attempt and lockout would never
    # trigger -- the defence would look present and do nothing.
    await session.commit()


async def authenticate(session: AsyncSession, *, email: str, password: str) -> User:
    """Verify credentials and return the user.

    Every failure raises the same error with the same message. An attacker must
    not be able to tell "no such account" from "wrong password" -- not from the
    response, and not from how long it took, which is why an unknown email
    still performs a hash (AUTH.md section 3.3).
    """
    now = datetime.now(UTC)
    users = UserRepository(session)
    user = await users.get_by_email(normalise_email(email))

    if user is None:
        verify_dummy_password()
        raise _invalid_credentials("unknown_email")

    if user.locked_until is not None and user.locked_until > now:
        verify_dummy_password()
        raise _invalid_credentials("locked_out")

    correct, needs_rehash = verify_password(user.password_hash, password)
    if not correct:
        await _register_failed_login(session, user, now)
        raise _invalid_credentials("wrong_password")

    if user.status is AccountStatus.SUSPENDED:
        raise ForbiddenError("This account is suspended.")

    if needs_rehash:
        # The configured cost has risen since this password was set. Upgrade it
        # now, while we hold the plaintext (AUTH.md section 3.1).
        user.password_hash = hash_password(password)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    await session.flush()
    return user


# ---------------------------------------------------------------------------
# Tokens (AUTH.md section 4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TokenPair:
    """What a successful login or refresh hands back."""

    access_token: str
    refresh_token: str
    expires_in: int


async def issue_tokens(
    session: AsyncSession, user: User, *, family_id: uuid.UUID | None = None
) -> TokenPair:
    """Mint an access token and a refresh token.

    `family_id` continues an existing session chain on refresh; omitted, it
    starts a new one for a fresh login.
    """
    settings = get_settings()
    raw_refresh = generate_refresh_token()

    await RefreshTokenRepository(session).create(
        user_id=user.id,
        family_id=family_id or uuid.uuid4(),
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
    )
    return TokenPair(
        access_token=create_access_token(user.id, user.role, settings=settings),
        refresh_token=raw_refresh,
        expires_in=settings.access_token_ttl_minutes * 60,
    )


def _invalid_refresh(reason: str) -> UnauthenticatedError:
    logger.info("refresh rejected", extra={"context": {"reason": reason}})
    return UnauthenticatedError("The refresh token is invalid or has expired.")


async def _handle_reuse(
    session: AsyncSession, stored: RefreshToken, now: datetime
) -> None:
    """Treat a replayed token as theft: end the whole session family."""
    revoked = await RefreshTokenRepository(session).revoke_family(
        stored.family_id, at=now
    )
    user = await UserRepository(session).get_by_id(stored.user_id)
    if user is not None:
        # Also kills every access token already issued for this session.
        user.session_valid_after = now
    await record_action(
        session,
        AuditAction.REFRESH_TOKEN_REUSE_DETECTED,
        actor_id=stored.user_id,
        target_type="user",
        target_id=stored.user_id,
        details={"family_id": str(stored.family_id), "tokens_revoked": revoked},
    )
    # Committed here for the same reason as a failed login, and it matters far
    # more: the caller raises straight after, the request fails, and the
    # rollback would undo the revocation. The client would receive a 401 while
    # the stolen token family stayed alive -- the control appearing to work
    # while doing nothing at all.
    await session.commit()
    logger.warning(
        "refresh token reuse detected; session family revoked",
        extra={"context": {"user_id": str(stored.user_id), "revoked": revoked}},
    )


async def refresh_tokens(session: AsyncSession, raw_token: str) -> TokenPair:
    """Rotate a refresh token.

    The important branch is reuse. A token that has already been exchanged,
    presented again, means it was captured -- either the thief is using it, or
    the legitimate client is replaying one the thief already spent. Either way
    the session is compromised, so the **entire family is revoked** and
    `session_valid_after` is bumped, which kills the access tokens too
    (AUTH.md section 4.2). That is what limits a stolen token to one use.
    """
    now = datetime.now(UTC)
    tokens = RefreshTokenRepository(session)
    stored = await tokens.get_by_hash(hash_refresh_token(raw_token))

    if stored is None:
        raise _invalid_refresh("unknown_token")

    if stored.used_at is not None:
        await _handle_reuse(session, stored, now)
        raise _invalid_refresh("reuse_detected")

    if stored.revoked_at is not None:
        raise _invalid_refresh("revoked")
    if stored.expires_at <= now:
        raise _invalid_refresh("expired")

    user = await UserRepository(session).get_by_id(stored.user_id)
    if user is None:
        raise _invalid_refresh("unknown_user")
    if user.status is AccountStatus.SUSPENDED:
        raise ForbiddenError("This account is suspended.")

    revoked_before = user.session_valid_after
    if revoked_before is not None and stored.issued_at < revoked_before:
        raise _invalid_refresh("session_revoked")

    pair = await issue_tokens(session, user, family_id=stored.family_id)
    successor = await tokens.get_by_hash(hash_refresh_token(pair.refresh_token))
    if successor is None:  # pragma: no cover - just written in this transaction
        raise _invalid_refresh("successor_missing")
    await tokens.mark_used(stored, replaced_by_id=successor.id, at=now)
    return pair


async def logout(session: AsyncSession, raw_token: str) -> None:
    """Revoke the presented token's family.

    Silent when the token is unknown: logout must not reveal whether a token
    was real, and the caller's intent is satisfied either way.
    """
    tokens = RefreshTokenRepository(session)
    stored = await tokens.get_by_hash(hash_refresh_token(raw_token))
    if stored is None:
        return
    await tokens.revoke_family(stored.family_id, at=datetime.now(UTC))


# ---------------------------------------------------------------------------
# The UserLoader `core.security` depends on -- T0.4's seam, now real
# ---------------------------------------------------------------------------


async def load_current_user(
    session: AsyncSession, user_id: uuid.UUID
) -> CurrentUser | None:
    """Resolve a verified token subject to the authoritative record."""
    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        return None
    return CurrentUser(
        id=user.id,
        role=user.role,
        status=user.status,
        email_verified=user.email_verified,
        session_valid_after=user.session_valid_after,
    )


# ---------------------------------------------------------------------------
# Email verification and password reset (AUTH.md sections 3.2, 12)
# ---------------------------------------------------------------------------

VERIFICATION_TTL: Final = timedelta(hours=24)
PASSWORD_RESET_TTL: Final = timedelta(hours=1)


def _link(path: str, token: str, settings: Settings) -> str:
    """Build a link the *client* handles, not this API.

    Mail security scanners prefetch every URL in a message. A GET endpoint here
    would have its single-use token consumed before the recipient ever clicked,
    so the link points at the app, which extracts the token and POSTs it back.
    """
    base = settings.app_link_base_url.rstrip("/")
    return f"{base}/{path}?token={token}"


async def issue_auth_token(
    session: AsyncSession, user: User, purpose: TokenPurpose, ttl: timedelta
) -> str:
    """Create a single-use token and return its raw value.

    Only the hash is persisted, so this return value is the only moment the
    token exists in readable form -- hand it straight to the message that
    carries it.
    """
    raw = generate_opaque_token()
    await AuthTokenRepository(session).create(
        user_id=user.id,
        purpose=purpose,
        token_hash=hash_opaque_token(raw),
        expires_at=datetime.now(UTC) + ttl,
    )
    return raw


def _invalid_link() -> InvalidRequestError:
    """One message for absent, expired, already-used, and wrong-purpose.

    Distinguishing them would tell a holder of a bad token which kind of bad it
    is, and whether the account exists at all.
    """
    return InvalidRequestError("This link is invalid or has expired.")


async def _consume(
    session: AsyncSession, raw_token: str, purpose: TokenPurpose
) -> tuple[AuthToken, User]:
    """Validate a token and return it with its user, or raise."""
    now = datetime.now(UTC)
    tokens = AuthTokenRepository(session)

    # Purpose is part of the lookup, so a verification token cannot be
    # presented as a password reset.
    stored = await tokens.get(token_hash=hash_opaque_token(raw_token), purpose=purpose)
    if stored is None:
        logger.info("auth token rejected", extra={"context": {"reason": "unknown"}})
        raise _invalid_link()
    if stored.used_at is not None:
        logger.info(
            "auth token rejected", extra={"context": {"reason": "already_used"}}
        )
        raise _invalid_link()
    if stored.expires_at <= now:
        logger.info("auth token rejected", extra={"context": {"reason": "expired"}})
        raise _invalid_link()

    user = await UserRepository(session).get_by_id(stored.user_id)
    if user is None:
        raise _invalid_link()
    return stored, user


async def send_verification_email(
    session: AsyncSession, user: User, *, settings: Settings | None = None
) -> None:
    """Issue a verification token and email the link.

    Failure to send is logged, not raised: registration must behave identically
    whether or not the email provider is reachable.
    """
    settings = settings or get_settings()
    raw = await issue_auth_token(
        session, user, TokenPurpose.EMAIL_VERIFICATION, VERIFICATION_TTL
    )
    await notifications.send_verification_email(
        user.email, _link("verify-email", raw, settings), settings=settings
    )


async def verify_email(session: AsyncSession, raw_token: str) -> User:
    """Confirm an address and activate the account."""
    stored, user = await _consume(session, raw_token, TokenPurpose.EMAIL_VERIFICATION)
    now = datetime.now(UTC)

    await AuthTokenRepository(session).mark_used(stored, at=now)
    user.email_verified_at = now
    # Only lift a *pending* account. Verifying an address must never quietly
    # un-suspend someone an admin has suspended.
    if user.status is AccountStatus.PENDING_VERIFICATION:
        user.status = AccountStatus.ACTIVE

    await record_action(
        session,
        AuditAction.USER_EMAIL_VERIFIED,
        actor_id=user.id,
        target_type="user",
        target_id=user.id,
    )
    await session.flush()
    return user


async def request_password_reset(
    session: AsyncSession, email: str, *, settings: Settings | None = None
) -> None:
    """Begin a reset. Returns nothing, whether or not the account exists.

    The caller responds identically either way (AUTH.md section 12) -- this
    endpoint must not become a way to test which addresses are registered.
    """
    settings = settings or get_settings()
    user = await UserRepository(session).get_by_email(normalise_email(email))
    if user is None:
        return

    raw = await issue_auth_token(
        session, user, TokenPurpose.PASSWORD_RESET, PASSWORD_RESET_TTL
    )
    await notifications.send_password_reset_email(
        user.email, _link("reset-password", raw, settings), settings=settings
    )


async def reset_password(
    session: AsyncSession, raw_token: str, new_password: str
) -> User:
    """Complete a reset and end every existing session.

    A password reset is what someone does when they believe their account is
    compromised, so it has to evict whoever might already be in: every refresh
    token is revoked and `session_valid_after` is bumped, which also kills
    access tokens already issued (AUTH.md section 11).
    """
    stored, user = await _consume(session, raw_token, TokenPurpose.PASSWORD_RESET)
    validate_password(new_password, user.email)
    now = datetime.now(UTC)

    user.password_hash = hash_password(new_password)
    user.session_valid_after = now
    user.failed_login_count = 0
    user.locked_until = None

    revoked = await RefreshTokenRepository(session).revoke_all_for_user(user.id, at=now)
    await AuthTokenRepository(session).mark_used(stored, at=now)
    # Any other reset link already in an inbox is now dead too.
    await AuthTokenRepository(session).consume_outstanding(
        user_id=user.id, purpose=TokenPurpose.PASSWORD_RESET, at=now
    )

    await record_action(
        session,
        AuditAction.USER_PASSWORD_RESET,
        actor_id=user.id,
        target_type="user",
        target_id=user.id,
        details={"sessions_revoked": revoked},
    )
    await session.flush()
    return user
