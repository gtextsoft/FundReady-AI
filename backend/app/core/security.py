"""Token verification and the identity it resolves to.

Authentication is **ours** (DECISIONS.md D4, D17) -- no managed identity
provider absorbs a mistake here on our behalf. `AUTH.md` is the spec.

This module is deliberately free of FastAPI: it decodes a token, resolves the
caller, and applies the account-level gates. The HTTP wiring lives in
`core.deps`. Password hashing (Argon2id) and token *issuance* for refresh
tokens arrive with T1.2.

The rules that matter, and why they are here rather than at each call site:

* **The signing algorithm is pinned from settings and never read from the
  token header.** Trusting the header is how `alg: none` and algorithm
  confusion get in -- an attacker rewrites the header and the token verifies.
* **`typ` is checked.** A refresh token must never be accepted where an access
  token is expected.
* **Role and status come from the loader, not the token.** A `role` claim rides
  along for convenience, but a decision is never made from it -- that is what
  makes a suspension or role change take effect on the next request instead of
  whenever the token happens to expire.
* **`session_valid_after` is honoured**, so bumping it revokes every access
  token already in the wild (AUTH.md section 11).
"""

import base64
import hashlib
import logging
import secrets
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import lru_cache
from typing import Any, Final, Protocol

import jwt
import pyotp
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError, ForbiddenError, UnauthenticatedError

logger = logging.getLogger(__name__)


class Role(StrEnum):
    """The three roles (AUTH.md section 2)."""

    FOUNDER = "founder"
    INVESTOR = "investor"
    ADMIN = "admin"


class AccountStatus(StrEnum):
    """Account lifecycle state (AUTH.md section 15)."""

    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class KycStatus(StrEnum):
    """Investor identity verification, trusted from Stripe only (AUTH.md 8)."""

    NONE = "none"
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


class SubscriptionStatus(StrEnum):
    """Founder billing state, trusted from Stripe webhooks only (AUTH.md 8)."""

    NONE = "none"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class TokenType(StrEnum):
    """The `typ` claim. Checked on every decode so the two never cross."""

    ACCESS = "access"
    REFRESH = "refresh"
    # Password accepted, second factor outstanding. Never grants access.
    MFA_CHALLENGE = "mfa_challenge"


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """The authenticated caller, as resolved from our own records."""

    id: uuid.UUID
    role: Role
    status: AccountStatus
    email_verified: bool = False
    mfa_enabled: bool = False
    session_valid_after: datetime | None = None


def assert_admin(actor: CurrentUser, *, message: str | None = None) -> None:
    """SACI admin, with a second factor. Both halves, one place.

    `require_role(Role.ADMIN)` enforces the same rule at the HTTP boundary
    (`core.deps`). Admin capabilities that reach a *service* without that
    dependency -- report reveal, benchmark writes, task reopen -- must call
    this, or an unenrolled admin holding a valid token can exercise them.
    AUTH.md section 9 and T1.2c require every admin capability behind MFA;
    a check retyped per module is a check that eventually loses one half.

    The unenrolled message matches `require_role` so the two layers answer
    the same way. `message` is reserved for the role half, so reopen can keep
    its existing wording without inventing a second MFA string.
    """
    if actor.role is not Role.ADMIN:
        raise ForbiddenError(message) if message else ForbiddenError()
    if not actor.mfa_enabled:
        raise ForbiddenError(
            "Admin accounts must enrol in two-factor authentication first."
        )


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """The verified contents of an access token."""

    subject: uuid.UUID
    issued_at: datetime
    token_id: str


class UserLoader(Protocol):
    """Loads the authoritative user record for a verified token subject.

    T1.2 supplies the repository-backed implementation. Until the `users` table
    exists this is the seam that keeps `core` from depending on a feature
    module, and it is what tests substitute.
    """

    def __call__(self, user_id: uuid.UUID) -> Awaitable[CurrentUser | None]:
        """Return the user, or None when no such active record exists."""
        ...


_user_loader: UserLoader | None = None


def set_user_loader(loader: UserLoader | None) -> None:
    """Register the loader used to resolve a token subject (or clear it)."""
    global _user_loader
    _user_loader = loader


def get_user_loader() -> UserLoader:
    if _user_loader is None:
        # Refusing to serve is correct: without a loader we could only trust
        # the token's own claims, which is exactly what we do not do.
        raise ConfigurationError
    return _user_loader


def _signing_key(settings: Settings) -> str:
    if settings.jwt_secret_key is None:
        raise ConfigurationError
    key = settings.jwt_secret_key.get_secret_value()
    if not key.strip():
        raise ConfigurationError
    return key


def create_access_token(
    user_id: uuid.UUID,
    role: Role,
    *,
    settings: Settings | None = None,
    issued_at: datetime | None = None,
    expires_in: timedelta | None = None,
) -> str:
    """Mint a short-lived access token (AUTH.md section 4.1)."""
    settings = settings or get_settings()
    now = issued_at or datetime.now(UTC)
    ttl = expires_in or timedelta(minutes=settings.access_token_ttl_minutes)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "typ": TokenType.ACCESS.value,
        "role": role.value,  # convenience only -- never authoritative
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(
        payload,
        _signing_key(settings),
        algorithm=settings.jwt_algorithm,
        headers={"kid": settings.jwt_key_id},
    )


def _reject(reason: str) -> UnauthenticatedError:
    """Log why a token was refused -- never the token itself."""
    logger.info("access token rejected", extra={"context": {"reason": reason}})
    return UnauthenticatedError("The access token is missing, invalid, or expired.")


def decode_access_token(
    token: str, settings: Settings | None = None
) -> AccessTokenClaims:
    """Verify an access token and return its claims.

    Raises `UnauthenticatedError` for every failure mode, with one message, so
    the response never tells an attacker *which* check failed.
    """
    settings = settings or get_settings()

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            _signing_key(settings),
            # Pinned. A token whose header claims another algorithm -- or
            # `none` -- fails here rather than being taken at its word.
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.InvalidTokenError as error:
        raise _reject(type(error).__name__) from None

    if payload.get("typ") != TokenType.ACCESS.value:
        raise _reject("wrong_token_type")

    try:
        subject = uuid.UUID(str(payload["sub"]))
    except (ValueError, KeyError):
        raise _reject("malformed_subject") from None

    return AccessTokenClaims(
        subject=subject,
        issued_at=datetime.fromtimestamp(int(payload["iat"]), tz=UTC),
        token_id=str(payload.get("jti", "")),
    )


async def resolve_current_user(
    token: str, settings: Settings | None = None
) -> CurrentUser:
    """Verify a token and resolve it to the caller behind it.

    Order matters (AUTH.md section 5): authenticated first, then account
    status. A suspended user holding a valid token is authenticated but not
    permitted -- 403, not 401, because refreshing would not help.

    Suspension is rejected here because it blocks everything (AUTH.md section
    8). `pending_verification` is *not* rejected here: `/v1/users/me` has to
    remain reachable so the client can tell the user to verify their email.
    Requiring an active account is `core.deps.get_current_user`.
    """
    claims = decode_access_token(token, settings)

    user = await get_user_loader()(claims.subject)
    if user is None:
        # The account was deleted, or the subject never existed. Same response
        # either way -- the client learns nothing about which.
        raise _reject("unknown_subject")

    # Revocation: bumping `session_valid_after` invalidates every token issued
    # before that moment, without waiting for expiry (AUTH.md section 11).
    revoked_before = user.session_valid_after
    if revoked_before is not None and claims.issued_at < revoked_before:
        raise _reject("session_revoked")

    if user.status is AccountStatus.SUSPENDED:
        raise ForbiddenError("This account is suspended.")

    return user


# ---------------------------------------------------------------------------
# Passwords (AUTH.md section 3.1)
# ---------------------------------------------------------------------------

# A hash of a fixed dummy password, verified against when the email is unknown
# so that "no such user" and "wrong password" take the same time. Computed once,
# lazily, because it costs a full Argon2 hash.
_dummy_hash: str | None = None


@lru_cache(maxsize=4)
def _hasher(memory_cost: int, time_cost: int, parallelism: int) -> PasswordHasher:
    return PasswordHasher(
        memory_cost=memory_cost,
        time_cost=time_cost,
        parallelism=parallelism,
        hash_len=32,
        salt_len=16,
        type=Type.ID,  # Argon2id -- not Argon2i or Argon2d
    )


def password_hasher(settings: Settings | None = None) -> PasswordHasher:
    """The Argon2id hasher, configured from settings so cost is tunable."""
    settings = settings or get_settings()
    return _hasher(
        settings.argon2_memory_cost_kib,
        settings.argon2_time_cost,
        settings.argon2_parallelism,
    )


def hash_password(password: str, settings: Settings | None = None) -> str:
    """Hash a password. The plaintext never leaves this call."""
    return password_hasher(settings).hash(password)


def verify_password(
    password_hash: str, password: str, settings: Settings | None = None
) -> tuple[bool, bool]:
    """Verify a password.

    Returns `(is_correct, needs_rehash)`. `needs_rehash` is true when the stored
    hash was produced with weaker parameters than are configured now, so login
    can transparently upgrade it (AUTH.md section 3.1).
    """
    hasher = password_hasher(settings)
    try:
        hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False, False
    return True, hasher.check_needs_rehash(password_hash)


def verify_dummy_password(settings: Settings | None = None) -> None:
    """Burn the same time as a real verification, for an unknown email.

    Without this, a failed lookup returns measurably faster than a failed
    password check, which turns login into an account-existence oracle.
    """
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("dummy-password-for-timing-parity", settings)
    verify_password(_dummy_hash, "not-the-dummy-password", settings)


# ---------------------------------------------------------------------------
# Refresh tokens (AUTH.md section 4.2)
# ---------------------------------------------------------------------------

OPAQUE_TOKEN_BYTES: Final = 32
REFRESH_TOKEN_BYTES: Final = OPAQUE_TOKEN_BYTES


def generate_opaque_token() -> str:
    """A high-entropy random token -- used for refresh, verification, reset.

    Not a JWT: these must be revocable, and a value the server stores is the
    only kind that can be.
    """
    return secrets.token_urlsafe(OPAQUE_TOKEN_BYTES)


def hash_opaque_token(token: str) -> str:
    """Hash an opaque token for storage.

    SHA-256 rather than Argon2 on purpose: the token is 256 bits of
    randomness, so there is nothing to brute-force and a slow hash would only
    make every use expensive. A database leak still yields nothing usable.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_refresh_token() -> str:
    """A refresh token (AUTH.md section 4.2)."""
    return generate_opaque_token()


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage."""
    return hash_opaque_token(token)


# ---------------------------------------------------------------------------
# MFA (AUTH.md section 9.1)
# ---------------------------------------------------------------------------

TOTP_DIGITS: Final = 6
TOTP_STEP_SECONDS: Final = 30
# One step either side, for clock drift between the phone and the server.
TOTP_DRIFT_STEPS: Final = 1
MFA_CHALLENGE_TTL: Final = timedelta(minutes=5)


def _fernet(settings: Settings) -> Fernet:
    """Build the cipher used for TOTP secrets at rest.

    The configured value is an arbitrary passphrase rather than a pre-formatted
    Fernet key, so it is stretched with HKDF instead of being truncated or
    padded -- an operator should not have to know Fernet's key encoding to run
    this service. Length is enforced in production by `validate_settings`.
    """
    if settings.mfa_secret_encryption_key is None:
        raise ConfigurationError
    raw = settings.mfa_secret_encryption_key.get_secret_value().encode("utf-8")
    if not raw.strip():
        raise ConfigurationError

    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"fundready-mfa-secret-v1",
    ).derive(raw)
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_mfa_secret(secret: str, settings: Settings | None = None) -> str:
    """Encrypt a TOTP secret for storage.

    Stored encrypted, not hashed: unlike a password we have to read it back to
    verify a code. A database leak alone must not hand over second factors
    (AUTH.md section 9.1).
    """
    return _fernet(settings or get_settings()).encrypt(secret.encode()).decode()


def decrypt_mfa_secret(payload: str, settings: Settings | None = None) -> str:
    """Recover a TOTP secret. Raises `ConfigurationError` if it cannot."""
    try:
        return _fernet(settings or get_settings()).decrypt(payload.encode()).decode()
    except InvalidToken:
        # Wrong key, or tampered ciphertext. Never echo either.
        logger.error("stored MFA secret could not be decrypted")
        raise ConfigurationError from None


def generate_mfa_secret() -> str:
    """A fresh base32 TOTP secret."""
    return pyotp.random_base32()


def mfa_provisioning_uri(secret: str, account: str, issuer: str) -> str:
    """The `otpauth://` URI an authenticator app scans as a QR code."""
    return pyotp.TOTP(
        secret, digits=TOTP_DIGITS, interval=TOTP_STEP_SECONDS
    ).provisioning_uri(name=account, issuer_name=issuer)


def verify_totp(
    secret: str, code: str, *, not_before_step: int | None = None
) -> int | None:
    """Check a TOTP code and return the step it matched, or None.

    Returns the matched step so the caller can persist it: `not_before_step`
    then rejects a code from that step or earlier, which is what stops an
    intercepted code being replayed inside its own 30-second window
    (AUTH.md section 9.1).

    Compared with `compare_digest` -- a timing-distinguishable comparison on a
    six-digit code is worth avoiding.
    """
    candidate = code.strip().replace(" ", "")
    if not candidate.isdigit() or len(candidate) != TOTP_DIGITS:
        return None

    totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_STEP_SECONDS)
    current = int(datetime.now(UTC).timestamp()) // TOTP_STEP_SECONDS

    for offset in range(-TOTP_DRIFT_STEPS, TOTP_DRIFT_STEPS + 1):
        step = current + offset
        if not secrets.compare_digest(totp.at(step * TOTP_STEP_SECONDS), candidate):
            continue
        if not_before_step is not None and step <= not_before_step:
            logger.info("totp rejected", extra={"context": {"reason": "replayed_step"}})
            return None
        return step
    return None


def create_mfa_challenge_token(
    user_id: uuid.UUID, *, settings: Settings | None = None
) -> str:
    """Bind the two halves of an MFA login together.

    Password verified, second factor outstanding. Short-lived and typed, so it
    cannot be used as an access token and `/auth/mfa/verify` cannot be called
    without having passed the password step first.
    """
    settings = settings or get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "typ": TokenType.MFA_CHALLENGE.value,
        "iat": int(now.timestamp()),
        "exp": int((now + MFA_CHALLENGE_TTL).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(
        payload,
        _signing_key(settings),
        algorithm=settings.jwt_algorithm,
        headers={"kid": settings.jwt_key_id},
    )


def decode_mfa_challenge_token(
    token: str, settings: Settings | None = None
) -> uuid.UUID:
    """Verify a challenge token and return its subject."""
    settings = settings or get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            _signing_key(settings),
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.InvalidTokenError as error:
        raise _reject(type(error).__name__) from None

    if payload.get("typ") != TokenType.MFA_CHALLENGE.value:
        raise _reject("wrong_token_type")
    try:
        return uuid.UUID(str(payload["sub"]))
    except (ValueError, KeyError):
        raise _reject("malformed_subject") from None
