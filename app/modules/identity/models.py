"""Identity ORM tables.

Layer: **models** (ARCHITECTURE.md section 3) -- SQLAlchemy table definitions
only. Every schema change also requires an Alembic migration under
`migrations/`; the database is never hand-edited.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


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
    REFRESH_TOKEN_REUSE_DETECTED = "user.refresh_token_reuse_detected"  # noqa: S105

    # Admin actions (AUTH.md section 9 -- all of these are logged)
    ADMIN_PROVISIONED = "admin.provisioned"
    USER_ROLE_CHANGED = "admin.user_role_changed"
    USER_SUSPENDED = "admin.user_suspended"
    USER_REACTIVATED = "admin.user_reactivated"

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
