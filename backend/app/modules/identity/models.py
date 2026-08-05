"""Identity ORM tables.

Layer: **models** (ARCHITECTURE.md section 3) -- SQLAlchemy table definitions
only. Every schema change also requires an Alembic migration under
`migrations/`; the database is never hand-edited.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, false, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.security import AccountStatus, KycStatus, Role, SubscriptionStatus


def _by_value(enum_class: type[StrEnum]) -> list[str]:
    """Store enum *values* ("founder"), not member names ("FOUNDER").

    SQLAlchemy defaults to names, which would make the database check
    constraint disagree with every value the API accepts and returns.
    """
    return [member.value for member in enum_class]


class AuditAction(StrEnum):
    """Actions recorded in the immutable audit log.

    Seeded with the events `AUTH.md` names explicitly -- every report reveal,
    tier change, purchase, and admin action. The set grows as tasks land, which
    is why the column is stored as text rather than a database enum: adding a
    value must not require a migration on an append-only table.
    """

    # Authentication and account lifecycle
    USER_REGISTERED = "user.registered"
    USER_LOGGED_IN = "user.logged_in"
    USER_LOGIN_FAILED = "user.login_failed"
    USER_EMAIL_VERIFIED = "user.email_verified"
    # noqa on the next two: flake8-bandit reads "password"/"token" in a
    # string literal as a credential. These are event names, not secrets.
    USER_PASSWORD_RESET = "user.password_reset"  # noqa: S105
    USER_SESSIONS_REVOKED = "user.sessions_revoked"
    USER_MFA_ENABLED = "user.mfa_enabled"
    USER_MFA_RECOVERY_CODE_USED = "user.mfa_recovery_code_used"
    REFRESH_TOKEN_REUSE_DETECTED = "user.refresh_token_reuse_detected"  # noqa: S105

    # Admin actions (AUTH.md section 9 -- all of these are logged)
    ADMIN_PROVISIONED = "admin.provisioned"
    USER_ROLE_CHANGED = "admin.user_role_changed"
    USER_SUSPENDED = "admin.user_suspended"
    USER_REACTIVATED = "admin.user_reactivated"

    # Benchmark knowledge base (T2.3). Logged because a benchmark is the
    # yardstick every verdict is measured against -- a bad row is a wrong
    # verdict for every startup scored against it, so who changed it matters.
    BENCHMARK_CREATED = "admin.benchmark_created"
    BENCHMARK_UPDATED = "admin.benchmark_updated"
    BENCHMARK_RETIRED = "admin.benchmark_retired"

    # Brokerage (T4.5). Logged because SACI standing between an investor and a
    # founder is the product, so who asked and who decided has to be
    # reconstructable afterwards -- including the declines.
    INTEREST_EXPRESSED = "brokerage.interest_expressed"
    INTEREST_APPROVED = "brokerage.interest_approved"
    INTEREST_DECLINED = "brokerage.interest_declined"

    # Readiness (T3.5). A reopen resets a founder's assessment attempts, which
    # is the only way past the cap that guards the investor-visibility gate --
    # so the one action that can undo it is recorded with who did it.
    TASK_REOPENED = "admin.task_reopened"

    # The one that matters most (DECISIONS.md D8)
    REPORT_REVEALED = "report.revealed"
    REPORT_TIER_CHANGED = "report.tier_changed"

    # Commerce
    PURCHASE_COMPLETED = "commerce.purchase_completed"
    SUBSCRIPTION_CHANGED = "commerce.subscription_changed"


class AuditLog(Base):
    """An append-only record of every security-significant action.

    Required by the PRD (section 5), `CLAUDE.md` section 4, and `AUTH.md`
    sections 9/13/15. Immutability is enforced *by the database* -- a trigger
    rejects UPDATE, DELETE, and TRUNCATE (see migration `0002_audit_log`) --
    because a log that the application merely promises not to modify is not
    evidence of anything.

    **No foreign key on `actor_id`, deliberately.** The log has to outlive the
    user it refers to: an FK would either block that user's deletion or cascade
    the evidence away with them. It stores the id and nothing more.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # Null for system-originated actions (a Stripe webhook, a scheduled job).
    actor_id: Mapped[uuid.UUID | None] = mapped_column(index=True)

    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(64), index=True)

    # `metadata` is reserved by SQLAlchemy's declarative base, so the attribute
    # is `details` while the column keeps the name `AUTH.md` section 15 gives it.
    details: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} actor={self.actor_id} at={self.created_at}>"


class User(Base):
    """A founder, investor, or SACI admin.

    The source of truth for role and account status: `AUTH.md` section 3.4
    requires both to be read from here on every request, never from a token
    claim, so a suspension or role change takes effect immediately.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # Stored already normalised (lower-cased, trimmed) by the service, so the
    # unique index is the actual guarantee against duplicate accounts.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))

    # Collected at self-service registration, so every founder and investor has
    # them. **Nullable anyway**, for two populations that never went through
    # that form: accounts created before this column existed, and admins, who
    # are provisioned by another admin (AUTH.md section 3.2) and whose
    # provisioning request does not ask for a name. A NOT NULL column would
    # need a fabricated backfill value for both, and an invented name is worse
    # than an absent one -- it looks like data.
    #
    # PII. Returned only to the account's owner and to SACI admins, and never
    # written to the audit log or any log line (CLAUDE.md section 4).
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))

    role: Mapped[Role] = mapped_column(
        SAEnum(
            Role,
            native_enum=False,
            length=16,
            name="user_role",
            values_callable=_by_value,
        )
    )
    status: Mapped[AccountStatus] = mapped_column(
        SAEnum(
            AccountStatus,
            native_enum=False,
            length=32,
            name="account_status",
            values_callable=_by_value,
        ),
        default=AccountStatus.PENDING_VERIFICATION,
    )

    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    mfa_enabled: Mapped[bool] = mapped_column(default=False, server_default=false())
    # Encrypted, not hashed: a TOTP secret has to be read back to verify a
    # code (AUTH.md section 9.1).
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(String(255))
    # The last TOTP step consumed. Rejecting codes from this step or earlier
    # is what stops an intercepted code being replayed inside its own
    # 30-second window. Not in AUTH.md section 15's list; section 9.1
    # requires the behaviour, so the column is added and the doc updated.
    mfa_last_used_step: Mapped[int | None] = mapped_column(BigInteger)

    # Both are trusted from Stripe only -- never from a client (AUTH.md 8).
    kyc_status: Mapped[KycStatus] = mapped_column(
        SAEnum(
            KycStatus,
            native_enum=False,
            length=16,
            name="kyc_status",
            values_callable=_by_value,
        ),
        default=KycStatus.NONE,
    )
    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(
            SubscriptionStatus,
            native_enum=False,
            length=16,
            name="subscription_status",
            values_callable=_by_value,
        ),
        default=SubscriptionStatus.NONE,
    )

    # Bumping this invalidates every access token issued before it, without
    # waiting for expiry (AUTH.md section 11).
    session_valid_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    failed_login_count: Mapped[int] = mapped_column(default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # `onupdate` is a Python callable, not `func.now()`. A server-side
    # onupdate leaves the ORM not knowing the new value, so it expires the
    # attribute and reading it back for a response triggers lazy IO --
    # which under async SQLAlchemy raises MissingGreenlet. Computing it here
    # means the value is sent as a parameter and already known.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    def __repr__(self) -> str:
        # Deliberately no email: __repr__ ends up in tracebacks and logs.
        return f"<User {self.id} role={self.role} status={self.status}>"


class RefreshToken(Base):
    """One issued refresh token.

    Rotating: each use marks this row `used_at` and issues a successor. If a
    row that already has `used_at` is presented again, the token was stolen --
    the whole `family_id` is revoked (AUTH.md section 4.2). That is what limits
    a stolen token to a single use.

    Only the SHA-256 hash is stored; the raw value exists once, in the response
    that issued it.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Unlike audit_log, a foreign key is right here: sessions are meaningless
    # once the user is gone, and should go with them.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Every token descended from one login shares this. Revoking it ends the
    # entire chain, not just the token that was replayed.
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)

    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column()

    def __repr__(self) -> str:
        return f"<RefreshToken {self.id} user={self.user_id} family={self.family_id}>"


class TokenPurpose(StrEnum):
    """What a single-use auth token is allowed to do.

    Checked on every lookup. Without it a verification token would also work as
    a password reset -- an attacker who obtains the weaker one gets the
    stronger capability for free.
    """

    EMAIL_VERIFICATION = "email_verification"
    # noqa: an enum member naming a flow, not a credential.
    PASSWORD_RESET = "password_reset"  # noqa: S105


class AuthToken(Base):
    """A single-use, expiring token sent by email (AUTH.md sections 12, 15).

    Only the SHA-256 hash is stored; the raw value exists once, in the message
    that carried it. Consumed by setting `used_at` -- rows are kept rather than
    deleted so a replay can be told apart from a token that never existed.
    """

    __tablename__ = "auth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[TokenPurpose] = mapped_column(
        SAEnum(
            TokenPurpose,
            native_enum=False,
            length=32,
            name="token_purpose",
            values_callable=_by_value,
        ),
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<AuthToken {self.id} purpose={self.purpose} user={self.user_id}>"


class MfaRecoveryCode(Base):
    """A single-use way back in when the authenticator device is gone.

    Stored Argon2id-hashed, exactly like a password: these are credentials, and
    ten of them are a standing bypass of the second factor if leaked
    (AUTH.md section 9.1).
    """

    __tablename__ = "mfa_recovery_codes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(255))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<MfaRecoveryCode {self.id} user={self.user_id} used={self.used_at}>"
