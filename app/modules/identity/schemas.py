"""Identity request/response schemas.

Layer: **schemas** (ARCHITECTURE.md section 3) -- Pydantic request and response
models, including the per-tier response serializers (summary vs full). Unknown
or extra fields are rejected. Tier filtering lives here and is enforced by the
service, never by the client (DECISIONS.md D8).

`Role` and `AccountStatus` are defined in `core.security` rather than here:
authentication is a cross-cutting concern and `core` must not import a feature
module. They are re-exported so schemas and routers have one obvious place to
reach for them (AGENTS.md section 4 -- enums are enums, never magic strings).
"""

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import AccountStatus, KycStatus, Role, SubscriptionStatus

__all__ = [
    "AccountStatus",
    "PasswordResetConfirmRequest",
    "PasswordResetRequest",
    "KycStatus",
    "LoginRequest",
    "LogoutRequest",
    "RefreshRequest",
    "RegisterRequest",
    "RegistrationAccepted",
    "Role",
    "SubscriptionStatus",
    "TokenPairResponse",
    "UserResponse",
    "VerifyEmailRequest",
]

# Deliberately permissive. Address syntax is not what makes an address real --
# the verification email is (T1.2b). This rejects the obviously malformed
# without pulling in a dependency to litigate RFC 5322.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")

Password = Annotated[str, Field(min_length=12, max_length=256)]


class _Request(BaseModel):
    """Base for request bodies: unknown fields are an error, not ignored."""

    model_config = ConfigDict(extra="forbid")


class _EmailMixin(_Request):
    email: str = Field(max_length=320, examples=["founder@example.com"])

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        normalised = value.strip().lower()
        if not _EMAIL_PATTERN.match(normalised):
            raise ValueError("not a valid email address")
        return normalised


class RegisterRequest(_EmailMixin):
    """Create a founder or investor account.

    `admin` is intentionally absent: admins are provisioned by an existing
    admin and never through self-service (AUTH.md section 3.2).
    """

    password: Password = Field(
        description="At least 12 characters. Must not contain your email address.",
    )
    role: Literal[Role.FOUNDER, Role.INVESTOR] = Field(
        description="`founder` or `investor`. Admin accounts cannot be self-created.",
    )


class RegistrationAccepted(BaseModel):
    """Deliberately uninformative.

    The same body is returned whether or not the address was already
    registered, so this endpoint cannot be used to discover who has an account.
    """

    status: Literal["pending_verification"] = "pending_verification"
    message: str = (
        "If that address can be registered, a verification email is on its way."
    )


class LoginRequest(_EmailMixin):
    password: str = Field(max_length=256)


class RefreshRequest(_Request):
    refresh_token: str = Field(max_length=512)


class LogoutRequest(_Request):
    refresh_token: str = Field(max_length=512)


class TokenPairResponse(BaseModel):
    """The tokens, and how the client should treat them.

    Store both in secure device storage. On `401`, exchange the refresh token
    once and retry; if that fails, send the user to login (AUTH.md section 16).
    """

    access_token: str
    refresh_token: str
    # noqa: the literal is the OAuth token *type*, not a credential.
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int = Field(
        description="Seconds until the access token expires.", examples=[900]
    )


class UserResponse(BaseModel):
    """The caller's own account. Never another user's."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: Role
    status: AccountStatus
    email_verified: bool
    kyc_status: KycStatus
    subscription_status: SubscriptionStatus
    created_at: datetime


class VerifyEmailRequest(_Request):
    """The token from the verification link."""

    token: str = Field(max_length=512)


class PasswordResetRequest(_EmailMixin):
    """Begin a reset. The response is the same whether or not the account exists."""


class PasswordResetConfirmRequest(_Request):
    """Complete a reset with the token from the emailed link."""

    token: str = Field(max_length=512)
    password: Password = Field(
        description="The new password. At least 12 characters.",
    )
