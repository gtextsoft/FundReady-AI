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
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.email_domains import is_consumer_domain, is_disposable_domain
from app.core.errors import (
    ConfigurationError,
    ConflictError,
    ForbiddenError,
    InvalidRequestError,
    NotFoundError,
    UnauthenticatedError,
)
from app.core.logging import get_request_id
from app.core.security import (
    AccountStatus,
    CurrentUser,
    Role,
    create_access_token,
    decode_mfa_challenge_token,
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_mfa_secret,
    generate_opaque_token,
    generate_refresh_token,
    generate_verification_code,
    hash_opaque_token,
    hash_password,
    hash_refresh_token,
    hash_verification_code,
    mfa_provisioning_uri,
    verification_codes_match,
    verify_dummy_password,
    verify_password,
    verify_totp,
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
    MfaRecoveryCodeRepository,
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
    session: AsyncSession,
    *,
    email: str,
    password: str,
    role: Role,
    first_name: str,
    last_name: str,
) -> User | None:
    """Register a founder or investor.

    Returns the new user, or **None when the email is already registered** --
    and the caller must respond identically either way. `AUTH.md` section 3.2
    requires it: any difference here turns registration into an
    account-existence oracle. Telling the real owner that someone tried is the
    job of the email, which arrives with T1.2a.

    **Founders must use a company address** (`DECISIONS.md` D20). Investors are
    not held to it: an angel investing personally has no company domain to give,
    and the KYC gate in T4.1 is what establishes who they are.
    """
    if role not in SELF_SERVICE_ROLES:
        # The message does not name the admin role: that would advertise its
        # existence to anyone poking at the endpoint.
        raise ForbiddenError("That account type cannot be created here.")

    normalised = normalise_email(email)

    # Refused before the duplicate check, and openly rather than through the
    # uniform response above. The two are not in tension: this answer is about
    # the *domain*, which the caller already knows, and reveals nothing about
    # whether any account exists. Saying "that address is fine, but silently
    # nothing happened" would be the worse outcome -- the founder would sit
    # waiting for an email that was never going to arrive.
    # **Every role, not just founders.** The consumer rule below is about
    # identity and D20 exempts investors from it; this one is about account
    # takeover and exempts nobody. Most throwaway inboxes are publicly readable
    # -- a mailinator address has no password -- so an account on one hands its
    # verification code, and every future password-reset link, to anyone who
    # knows the address. An investor reading summary-tier startup data through a
    # public mailbox is the same breach as a founder doing it.
    if is_disposable_domain(normalised):
        raise InvalidRequestError(
            "That email provider cannot be used here. Please register with an "
            "address you control privately.",
            {"field": "email", "reason": "disposable_email_domain"},
        )

    if role is Role.FOUNDER and is_consumer_domain(normalised):
        raise InvalidRequestError(
            "Use your company email address to register as a founder.",
            {"field": "email", "reason": "consumer_email_domain"},
        )

    validate_password(password, normalised)

    users = UserRepository(session)
    if await users.get_by_email(normalised) is not None:
        return None

    user = await users.create(
        email=normalised,
        password_hash=hash_password(password),
        role=role,
        status=AccountStatus.PENDING_VERIFICATION,
        first_name=first_name,
        last_name=last_name,
    )
    # `details` carries the role and nothing else. The name is PII and the
    # audit log is append-only and broadly readable by admins -- putting it
    # here would copy personal data into a record that can never be corrected
    # or deleted (CLAUDE.md section 4). Who registered is already the
    # `actor_id`; what they are called is on the user row.
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
        mfa_enabled=user.mfa_enabled,
        session_valid_after=user.session_valid_after,
    )


async def get_user_email(session: AsyncSession, user_id: uuid.UUID) -> str | None:
    """This user's address, for another module that needs the domain.

    `intake` reads the company name off a founder's verified domain (D20) and
    cannot reach `UserRepository` itself (`ARCHITECTURE.md` section 3), so the
    lookup is exposed here rather than the repository being shared.

    Deliberately narrow: it returns the address and nothing else. A general
    "give me the user" accessor across module boundaries is how another
    module's code starts depending on this one's model, and how fields nobody
    audited start travelling.

    The caller is trusted server code. This performs **no** authorization --
    callers pass a `user_id` they have already established a right to, which in
    `intake`'s case is the caller's own id from the verified token.
    """
    user = await UserRepository(session).get_by_id(user_id)
    return user.email if user is not None else None


# ---------------------------------------------------------------------------
# Email verification and password reset (AUTH.md sections 3.2, 12)
# ---------------------------------------------------------------------------

# Short, deliberately. A 24-hour window suited a 256-bit link that nobody was
# going to guess; a six-digit code is a million combinations, so the window in
# which those guesses are worth making is kept to the few minutes it takes
# someone to read an email (AUTH.md section 3.2).
VERIFICATION_TTL: Final = timedelta(minutes=15)
PASSWORD_RESET_TTL: Final = timedelta(hours=1)

# Five wrong guesses burn the code. With the code also expiring in 15 minutes
# and being bound to one account, that caps an attacker at five of a million
# combinations per code -- and each fresh code costs them an email they cannot
# read. Generous enough that a person mistyping twice is not locked out.
MAX_VERIFICATION_ATTEMPTS: Final = 5

# How long a live code suppresses another send. Without it, "resend" is a
# button that mails somebody else's inbox as fast as it can be pressed. Real
# per-IP and per-account rate limiting is T5.5; this is the floor beneath it.
VERIFICATION_RESEND_COOLDOWN: Final = timedelta(seconds=60)

# A code hash is keyed with the user id, so two rows colliding needs the same
# user to draw the same six digits twice. Regenerating is cheaper than letting
# that raise a unique-constraint violation on the one path a new account walks.
_CODE_COLLISION_RETRIES: Final = 5


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


def _invalid_code() -> InvalidRequestError:
    """One message for wrong, expired, spent, exhausted, and no-such-account.

    Same reasoning as `_invalid_link`, with one addition that matters more
    here: the code is checked against an address the caller supplied, so a
    distinct "no account for that email" would turn this endpoint into the
    account-existence oracle registration is written to avoid
    (AUTH.md section 3.2).
    """
    return InvalidRequestError("That code is invalid or has expired.")


async def issue_verification_code(
    session: AsyncSession, user: User, *, settings: Settings | None = None
) -> str:
    """Create a verification code and return it, for the email to carry.

    Any code already outstanding is burned first, so there is exactly one live
    code per account. Two live codes would double an attacker's guesses per
    email and leave a person typing the older one wondering why it failed.

    Only the keyed hash is persisted, so this return value is the one moment
    the code exists in readable form.
    """
    settings = settings or get_settings()
    tokens = AuthTokenRepository(session)
    now = datetime.now(UTC)

    await tokens.consume_outstanding(
        user_id=user.id, purpose=TokenPurpose.EMAIL_VERIFICATION, at=now
    )

    for _ in range(_CODE_COLLISION_RETRIES):
        code = generate_verification_code()
        code_hash = hash_verification_code(
            code,
            user_id=user.id,
            purpose=TokenPurpose.EMAIL_VERIFICATION.value,
            settings=settings,
        )
        already_used = await tokens.get(
            token_hash=code_hash, purpose=TokenPurpose.EMAIL_VERIFICATION
        )
        if already_used is not None:
            continue
        await tokens.create(
            user_id=user.id,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            token_hash=code_hash,
            expires_at=now + VERIFICATION_TTL,
        )
        return code

    # Five collisions in a row is not something that happens; treating it as a
    # server error is better than looping until one of them stops.
    raise ConfigurationError


async def send_verification_email(
    session: AsyncSession, user: User, *, settings: Settings | None = None
) -> None:
    """Issue a verification code and email it.

    Failure to send is logged, not raised: registration must behave identically
    whether or not the email provider is reachable.
    """
    settings = settings or get_settings()
    code = await issue_verification_code(session, user, settings=settings)
    await notifications.send_verification_email(
        user.email,
        code,
        ttl_minutes=int(VERIFICATION_TTL.total_seconds() // 60),
        settings=settings,
    )


async def resend_verification_email(
    session: AsyncSession, email: str, *, settings: Settings | None = None
) -> None:
    """Send another code. Returns nothing, whatever the address turns out to be.

    Silent for an unknown address, for an already-verified one, and while a
    recent code is still live -- the caller cannot tell those apart from a
    successful send, so this cannot be used to discover who has an account or
    who has finished verifying.
    """
    settings = settings or get_settings()
    user = await UserRepository(session).get_by_email(normalise_email(email))
    if user is None or user.email_verified:
        return

    now = datetime.now(UTC)
    live = await AuthTokenRepository(session).latest_live(
        user_id=user.id, purpose=TokenPurpose.EMAIL_VERIFICATION, now=now
    )
    if live is not None and live.expires_at - VERIFICATION_TTL > (
        now - VERIFICATION_RESEND_COOLDOWN
    ):
        logger.info("verification resend suppressed by cooldown")
        return

    await send_verification_email(session, user, settings=settings)


async def verify_email(
    session: AsyncSession, *, email: str, code: str, settings: Settings | None = None
) -> User:
    """Confirm an address with the code that was emailed, and activate it.

    The address is part of the request because the code is only six digits: it
    is checked against one account rather than looked up globally, so the
    million combinations have to be spent against a single target instead of
    matching whichever account happens to hold them.
    """
    settings = settings or get_settings()
    now = datetime.now(UTC)

    user = await UserRepository(session).get_by_email(normalise_email(email))
    if user is None:
        logger.info("verification rejected", extra={"context": {"reason": "no_user"}})
        raise _invalid_code()

    tokens = AuthTokenRepository(session)
    stored = await tokens.latest_live(
        user_id=user.id, purpose=TokenPurpose.EMAIL_VERIFICATION, now=now
    )
    if stored is None:
        logger.info("verification rejected", extra={"context": {"reason": "no_code"}})
        raise _invalid_code()

    candidate = hash_verification_code(
        code,
        user_id=user.id,
        purpose=TokenPurpose.EMAIL_VERIFICATION.value,
        settings=settings,
    )
    if not verification_codes_match(candidate, stored.token_hash):
        attempts = await tokens.record_failed_attempt(stored)
        exhausted = attempts >= MAX_VERIFICATION_ATTEMPTS
        if exhausted:
            # Burned, not merely counted: the next request must start from a
            # freshly emailed code, which is the thing an attacker cannot read.
            await tokens.mark_used(stored, at=now)
        # Committed here rather than left to the request, for the same reason
        # as a failed login: the caller raises next, and the rollback would
        # discard the count. The cap would look present and stop nothing.
        await session.commit()
        logger.info(
            "verification rejected",
            extra={"context": {"reason": "wrong_code", "exhausted": exhausted}},
        )
        raise _invalid_code()

    await tokens.mark_used(stored, at=now)
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


# ---------------------------------------------------------------------------
# MFA (AUTH.md section 9.1)
# ---------------------------------------------------------------------------

RECOVERY_CODE_COUNT: Final = 10
RECOVERY_CODE_BYTES: Final = 5  # 10 hex chars, shown as XXXXX-XXXXX


@dataclass(frozen=True, slots=True)
class MfaEnrolment:
    """What the client needs to finish enrolling. Not yet active."""

    secret: str
    provisioning_uri: str


def _format_recovery_code(raw: str) -> str:
    return f"{raw[:5]}-{raw[5:]}".upper()


def generate_recovery_codes() -> list[str]:
    """Ten codes, returned once and never recoverable afterwards."""
    return [
        _format_recovery_code(secrets.token_hex(RECOVERY_CODE_BYTES))
        for _ in range(RECOVERY_CODE_COUNT)
    ]


async def start_mfa_enrolment(
    session: AsyncSession, user: User, *, settings: Settings | None = None
) -> MfaEnrolment:
    """Issue a secret to enrol against, without enabling anything.

    `mfa_enabled` stays false until a code proves the authenticator actually
    holds the secret -- otherwise a mistyped setup locks the user out of their
    own account (AUTH.md section 9.1).
    """
    settings = settings or get_settings()
    secret = generate_mfa_secret()
    user.mfa_secret_encrypted = encrypt_mfa_secret(secret, settings)
    user.mfa_enabled = False
    await session.flush()

    return MfaEnrolment(
        secret=secret,
        provisioning_uri=mfa_provisioning_uri(secret, user.email, settings.jwt_issuer),
    )


async def confirm_mfa_enrolment(
    session: AsyncSession, user: User, code: str, *, settings: Settings | None = None
) -> list[str]:
    """Enable MFA once a code checks out, and return the recovery codes.

    The returned codes are the only copy -- they are stored hashed.
    """
    settings = settings or get_settings()
    if user.mfa_secret_encrypted is None:
        raise InvalidRequestError("Start enrolment before confirming it.")

    secret = decrypt_mfa_secret(user.mfa_secret_encrypted, settings)
    step = verify_totp(secret, code, not_before_step=user.mfa_last_used_step)
    if step is None:
        raise InvalidRequestError("That code is not valid.")

    user.mfa_enabled = True
    user.mfa_last_used_step = step

    codes = generate_recovery_codes()
    await MfaRecoveryCodeRepository(session).replace_all(
        user_id=user.id,
        code_hashes=[hash_password(code_value, settings) for code_value in codes],
    )
    await record_action(
        session,
        AuditAction.USER_MFA_ENABLED,
        actor_id=user.id,
        target_type="user",
        target_id=user.id,
    )
    await session.flush()
    return codes


async def _consume_recovery_code(
    session: AsyncSession, user: User, code: str, now: datetime
) -> bool:
    """Spend a recovery code, if the value matches an unused one."""
    candidate = code.strip().upper()
    repository = MfaRecoveryCodeRepository(session)
    for stored in await repository.list_unused(user_id=user.id):
        correct, _ = verify_password(stored.code_hash, candidate)
        if correct:
            await repository.mark_used(stored, at=now)
            await record_action(
                session,
                AuditAction.USER_MFA_RECOVERY_CODE_USED,
                actor_id=user.id,
                target_type="user",
                target_id=user.id,
            )
            return True
    return False


async def verify_mfa_challenge(
    session: AsyncSession, challenge_token: str, code: str
) -> TokenPair:
    """Complete a login that stopped at the second factor.

    Accepts a TOTP code or a recovery code. Every failure returns the same
    error: which kind of credential was wrong is not the caller's business.
    """
    user_id = decode_mfa_challenge_token(challenge_token)
    user = await UserRepository(session).get_by_id(user_id)
    if user is None or not user.mfa_enabled or user.mfa_secret_encrypted is None:
        raise _invalid_mfa("no_enrolment")
    if user.status is AccountStatus.SUSPENDED:
        raise ForbiddenError("This account is suspended.")

    now = datetime.now(UTC)
    step = verify_totp(
        decrypt_mfa_secret(user.mfa_secret_encrypted),
        code,
        not_before_step=user.mfa_last_used_step,
    )
    if step is not None:
        user.mfa_last_used_step = step
    elif not await _consume_recovery_code(session, user, code, now):
        # Committed for the same reason as a failed password: the caller raises
        # next, and the rollback would discard a spent recovery code.
        await session.commit()
        raise _invalid_mfa("wrong_code")

    user.last_login_at = now
    await session.flush()
    return await issue_tokens(session, user)


def _invalid_mfa(reason: str) -> UnauthenticatedError:
    logger.info("mfa verification failed", extra={"context": {"reason": reason}})
    return UnauthenticatedError("That code is not valid.")


# ---------------------------------------------------------------------------
# Admin user management (AUTH.md section 9)
# ---------------------------------------------------------------------------


def _require_admin(actor: CurrentUser) -> None:
    """Re-check the actor's role in the service layer.

    The route dependency already enforced this. Checking again here is the
    defence-in-depth `CLAUDE.md` section 4 asks for: these functions are also
    callable from a script or another module, where no dependency ran.
    """
    if actor.role is not Role.ADMIN:
        raise ForbiddenError


async def _load_target(session: AsyncSession, user_id: uuid.UUID) -> User:
    target = await UserRepository(session).get_by_id(user_id)
    if target is None:
        raise NotFoundError("No such user.")
    return target


async def _refuse_if_last_active_admin(session: AsyncSession, target: User) -> None:
    """Stop an action that would leave the platform with no administrators.

    The escape hatch would be `scripts/create_admin.py` and database
    credentials, which is not a position to put an operator in.
    """
    if target.role is not Role.ADMIN or target.status is not AccountStatus.ACTIVE:
        return
    if await UserRepository(session).count_active_admins() <= 1:
        raise ConflictError("This is the only active admin account.")


async def provision_admin(
    session: AsyncSession,
    actor: CurrentUser,
    *,
    email: str,
    password: str,
) -> User:
    """Create an admin account. The only path that produces one.

    The new admin lands `pending_verification` and **without MFA**, so they must
    verify their address and enrol a second factor before any admin capability
    opens to them (AUTH.md section 9).

    Unlike self-registration, a duplicate address is a real error here: the
    caller is already a trusted admin, so there is no enumeration concern and
    silently doing nothing would be worse than saying so.
    """
    _require_admin(actor)

    normalised = normalise_email(email)
    validate_password(password, normalised)

    users = UserRepository(session)
    if await users.get_by_email(normalised) is not None:
        raise ConflictError("That email address already has an account.")

    admin = await users.create(
        email=normalised,
        password_hash=hash_password(password),
        role=Role.ADMIN,
        status=AccountStatus.PENDING_VERIFICATION,
    )
    await record_action(
        session,
        AuditAction.ADMIN_PROVISIONED,
        actor_id=actor.id,
        target_type="user",
        target_id=admin.id,
    )
    # No session_valid_after bump: the account has never had a session.
    await send_verification_email(session, admin)
    await session.flush()
    return admin


async def suspend_user(
    session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID
) -> User:
    """Suspend an account and end its sessions immediately.

    Suspension is what an admin reaches for when they believe an account is
    compromised, so it evicts rather than waits: every refresh token is revoked
    and `session_valid_after` is bumped, which kills access tokens already
    issued (AUTH.md section 11).
    """
    _require_admin(actor)
    if actor.id == user_id:
        raise ForbiddenError("You cannot suspend your own account.")

    target = await _load_target(session, user_id)
    await _refuse_if_last_active_admin(session, target)

    now = datetime.now(UTC)
    target.status = AccountStatus.SUSPENDED
    target.session_valid_after = now
    revoked = await RefreshTokenRepository(session).revoke_all_for_user(
        target.id, at=now
    )
    await record_action(
        session,
        AuditAction.USER_SUSPENDED,
        actor_id=actor.id,
        target_type="user",
        target_id=target.id,
        details={"sessions_revoked": revoked},
    )
    await session.flush()
    return target


async def reactivate_user(
    session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID
) -> User:
    """Lift a suspension.

    Restores `active` only if the address was verified; an account suspended
    while still pending returns to pending, not straight to active.

    No `session_valid_after` bump: the suspension already moved it, and moving
    it again would revoke nothing that is not already dead.
    """
    _require_admin(actor)

    target = await _load_target(session, user_id)
    if target.status is not AccountStatus.SUSPENDED:
        raise ConflictError("That account is not suspended.")

    target.status = (
        AccountStatus.ACTIVE
        if target.email_verified
        else AccountStatus.PENDING_VERIFICATION
    )
    await record_action(
        session,
        AuditAction.USER_REACTIVATED,
        actor_id=actor.id,
        target_type="user",
        target_id=target.id,
        details={"status": target.status.value},
    )
    await session.flush()
    return target


async def change_user_role(
    session: AsyncSession, actor: CurrentUser, user_id: uuid.UUID, new_role: Role
) -> User:
    """Change a user's role and force them to re-authenticate.

    `session_valid_after` is bumped because the change has to take effect now:
    `AUTH.md` section 11 lists a role change under force-logout. Refresh tokens
    issued before the bump stop working too, so the user logs in again and
    every subsequent request is authorised against the new role.
    """
    _require_admin(actor)
    if actor.id == user_id:
        raise ForbiddenError("You cannot change your own role.")

    target = await _load_target(session, user_id)
    if target.role is new_role:
        raise ConflictError("That user already has that role.")
    if new_role is not Role.ADMIN:
        await _refuse_if_last_active_admin(session, target)

    previous = target.role
    target.role = new_role
    target.session_valid_after = datetime.now(UTC)

    await record_action(
        session,
        AuditAction.USER_ROLE_CHANGED,
        actor_id=actor.id,
        target_type="user",
        target_id=target.id,
        details={"from": previous.value, "to": new_role.value},
    )
    await session.flush()
    return target
