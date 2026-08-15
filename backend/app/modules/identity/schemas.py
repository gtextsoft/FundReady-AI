"""Identity request/response schemas.

Layer: **schemas** (ARCHITECTURE.md section 3) -- Pydantic request and response
models, including the per-tier response serializers (summary vs full). Unknown
or extra fields are rejected. Tier filtering lives here and is enforced by the
service, never by the client (DECISIONS.md D8).

`Role` and `AccountStatus` are defined in `core.security` rather than here:
authentication is a cross-cutting concern and `core` must not import a feature
module. They are re-exported so schemas and routers have one obvious place to
reach for them (AGENTS.md section 4 -- enums are enums, never magic strings).

**Every model carries an example.** `CLAUDE.md` section 6 requires each endpoint
to publish at least one example request and response, and putting them on the
schema rather than the route means Swagger, ReDoc, and any generated client all
pick them up from one place. The values are obviously fake -- a real token would
be an invitation to paste it somewhere.
"""

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.entitlement import has_founder_access, trial_ends_at
from app.core.security import (
    VERIFICATION_CODE_DIGITS,
    AccountStatus,
    KycStatus,
    Role,
    SubscriptionStatus,
)

__all__ = [
    "AccountStatus",
    "ChangeRoleRequest",
    "KycStatus",
    "LoginRequest",
    "LoginResponse",
    "LogoutRequest",
    "MfaConfirmRequest",
    "MfaEnrolmentResponse",
    "MfaRecoveryCodesResponse",
    "MfaVerifyRequest",
    "PasswordResetConfirmRequest",
    "PasswordResetRequest",
    "ProvisionAdminRequest",
    "RefreshRequest",
    "RegisterRequest",
    "RegistrationAccepted",
    "ResendVerificationRequest",
    "Role",
    "SubscriptionStatus",
    "TokenPairResponse",
    "UserPage",
    "UserResponse",
    "VerifyEmailRequest",
]

# Deliberately permissive. Address syntax is not what makes an address real --
# the verification email is (T1.2b). This rejects the obviously malformed
# without pulling in a dependency to litigate RFC 5322.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")

Password = Annotated[str, Field(min_length=12, max_length=256)]

# Control characters only. There is deliberately **no alphabet restriction** --
# no `[A-Za-z]`, no "letters and hyphens only". This platform registers people
# in Nigeria, the UAE, the UK, the US, and China, and every such rule rejects
# real names: diacritics, non-Latin scripts, apostrophes, spaces, and single
# characters are all legitimate. The only thing filtered is what cannot be part
# of a name in any script.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f-\x9f]")

PersonName = Annotated[str, Field(min_length=1, max_length=100)]

# Shared example values, so the documentation tells one coherent story instead
# of a different invented user per endpoint. The `noqa: S105` markers below are
# flake8-bandit reading the variable names -- these are documentation strings
# that decode to nothing and verify against nothing.
EMAIL = "founder@example.com"
USER_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
FIRST_NAME = "Amaka"
LAST_NAME = "Okonkwo"
PASSWORD_EXAMPLE = "correct-horse-battery-staple"  # noqa: S105
ACCESS_EXAMPLE = "eyJhbGciOiJIUzI1NiIsImtpZCI6ImsxIn0.eyJzdWIiOiI3Yzll.EXAMPLE"
REFRESH_EXAMPLE = "N2Q4ZjFhYzQtM2I5ZS00ZjJhLTk4YzEtMGU3YjRkNmE5ZjEy"
VERIFICATION_CODE_EXAMPLE = "418305"
MFA_TOKEN_EXAMPLE = "eyJhbGciOiJIUzI1NiJ9.eyJ0eXAiOiJtZmFfY2hhbGxlbmdlIn0.EXAMPLE"  # noqa: S105
REGISTRATION_MESSAGE = (
    "If that address can be registered, a verification email is on its way."
)


def examples(*payloads: dict[str, Any]) -> ConfigDict:
    """`model_config` publishing one or more examples for a request body."""
    return ConfigDict(extra="forbid", json_schema_extra={"examples": list(payloads)})


def response_examples(*payloads: dict[str, Any]) -> ConfigDict:
    """As above, for responses -- which do not forbid extra fields."""
    return ConfigDict(json_schema_extra={"examples": list(payloads)})


class _Request(BaseModel):
    """Base for request bodies: unknown fields are an error, not ignored."""

    model_config = ConfigDict(extra="forbid")


class _EmailMixin(_Request):
    email: str = Field(max_length=320, examples=[EMAIL])

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

    A founder's address must be a company one (AUTH.md section 3.2). Enforced
    in the service, not here, because the rule depends on `role` and belongs
    with the rest of the registration policy.
    """

    model_config = examples(
        {
            "email": EMAIL,
            "password": PASSWORD_EXAMPLE,
            "role": "founder",
            "first_name": FIRST_NAME,
            "last_name": LAST_NAME,
        }
    )

    password: Password = Field(
        description="At least 12 characters. Must not contain your email address.",
    )
    role: Literal[Role.FOUNDER, Role.INVESTOR] = Field(
        description=(
            "`founder` or `investor`. Admin accounts cannot be self-created. "
            "A `founder` must use a company email address, not a consumer "
            "mailbox provider."
        ),
    )
    first_name: PersonName = Field(
        description="The person's given name. Required for founders and investors.",
        examples=[FIRST_NAME],
    )
    last_name: PersonName = Field(
        description="The person's family name. Required for founders and investors.",
        examples=[LAST_NAME],
    )

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def _clean_name(cls, value: Any) -> Any:
        """Trim and strip control characters *before* the length rules apply.

        Order matters: running this first means a whitespace-only name fails
        `min_length` as blank rather than passing as three spaces, and a name
        padded past 100 characters by trailing whitespace is accepted on its
        real length instead of being rejected for the padding.
        """
        if isinstance(value, str):
            return _CONTROL_CHARACTERS.sub("", value).strip()
        return value


class RegistrationAccepted(BaseModel):
    """Deliberately uninformative.

    The same body is returned whether or not the address was already
    registered, so this endpoint cannot be used to discover who has an account.
    """

    model_config = response_examples(
        {"status": "pending_verification", "message": REGISTRATION_MESSAGE}
    )

    status: Literal["pending_verification"] = "pending_verification"
    message: str = REGISTRATION_MESSAGE


class LoginRequest(_EmailMixin):
    """Email and password."""

    model_config = examples({"email": EMAIL, "password": PASSWORD_EXAMPLE})

    password: str = Field(max_length=256)


class RefreshRequest(_Request):
    """The refresh token to exchange. It is consumed by this call."""

    model_config = examples({"refresh_token": REFRESH_EXAMPLE})

    refresh_token: str = Field(max_length=512)


class LogoutRequest(_Request):
    """The refresh token whose family should be revoked."""

    model_config = examples({"refresh_token": REFRESH_EXAMPLE})

    refresh_token: str = Field(max_length=512)


class TokenPairResponse(BaseModel):
    """The tokens, and how the client should treat them.

    Store both in secure device storage. On `401`, exchange the refresh token
    once and retry; if that fails, send the user to login (AUTH.md section 16).
    """

    model_config = response_examples(
        {
            "access_token": ACCESS_EXAMPLE,
            "refresh_token": REFRESH_EXAMPLE,
            "token_type": "bearer",
            "expires_in": 900,
        }
    )

    access_token: str
    refresh_token: str
    # S105 below: the literal is the OAuth token *type*, not a credential.
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int = Field(
        description="Seconds until the access token expires.", examples=[900]
    )


class LoginResponse(BaseModel):
    """The outcome of a login attempt.

    **Branch on `status`.** `authenticated` means `tokens` is present and the
    session is live. `mfa_required` means the password was accepted but a second
    factor is outstanding: `mfa_token` is present instead, and must be sent to
    `POST /v1/auth/mfa/verify` together with the code. `mfa_token` is not an
    access token and grants nothing on its own.
    """

    # Both branches are published, because a client that only ever saw the happy
    # one would not know the other shape exists.
    model_config = response_examples(
        {
            "status": "authenticated",
            "tokens": {
                "access_token": ACCESS_EXAMPLE,
                "refresh_token": REFRESH_EXAMPLE,
                "token_type": "bearer",
                "expires_in": 900,
            },
            "mfa_token": None,
        },
        {"status": "mfa_required", "tokens": None, "mfa_token": MFA_TOKEN_EXAMPLE},
    )

    status: Literal["authenticated", "mfa_required"]
    tokens: TokenPairResponse | None = Field(
        default=None, description="Present when `status` is `authenticated`."
    )
    mfa_token: str | None = Field(
        default=None,
        description="Present when `status` is `mfa_required`. Expires in 5 minutes.",
    )


class UserResponse(BaseModel):
    """The caller's own account. Never another user's."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": USER_ID,
                    "email": EMAIL,
                    "role": "founder",
                    "first_name": FIRST_NAME,
                    "last_name": LAST_NAME,
                    "status": "pending_verification",
                    "email_verified": False,
                    "kyc_status": "none",
                    "subscription_status": "none",
                    "created_at": "2026-07-29T09:15:00Z",
                    "trial_ends_at": "2026-08-12T09:15:00Z",
                    "has_access": True,
                    "mfa_enabled": False,
                }
            ]
        },
    )

    id: uuid.UUID
    email: str
    role: Role
    # Nullable for the two populations that never saw the registration form:
    # accounts created before the column existed, and admins, who are
    # provisioned by another admin rather than self-registering. A client must
    # handle `null` -- see the note in `identity.models`.
    first_name: str | None
    last_name: str | None
    status: AccountStatus
    email_verified: bool
    kyc_status: KycStatus
    subscription_status: SubscriptionStatus
    created_at: datetime
    # Server-authoritative trial/entitlement (DECISIONS.md D24). Clients must
    # not recompute these from `created_at` with a local clock.
    trial_ends_at: datetime
    has_access: bool
    mfa_enabled: bool = False

    @classmethod
    def of(cls, user: Any) -> "UserResponse":
        """Build from a `User` ORM row, computing trial fields."""
        ends = trial_ends_at(user.created_at)
        access = (
            has_founder_access(
                subscription_status=user.subscription_status,
                created_at=user.created_at,
            )
            if user.role is Role.FOUNDER
            else True
        )
        return cls(
            id=user.id,
            email=user.email,
            role=user.role,
            first_name=user.first_name,
            last_name=user.last_name,
            status=user.status,
            email_verified=user.email_verified,
            kyc_status=user.kyc_status,
            subscription_status=user.subscription_status,
            created_at=user.created_at,
            trial_ends_at=ends,
            has_access=access,
            mfa_enabled=bool(user.mfa_enabled),
        )


class UserPage(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {"items": [], "total": 0, "limit": 20, "offset": 0}
        },
    )

    items: list[UserResponse]
    total: int
    limit: int
    offset: int


class VerifyEmailRequest(_EmailMixin):
    """The address being confirmed, and the code that was emailed to it.

    Both, always. The code is six digits, so it is checked against one account
    rather than looked up across all of them -- otherwise a guessed code would
    match whichever account happened to hold it (AUTH.md section 3.2).
    """

    model_config = examples({"email": EMAIL, "code": VERIFICATION_CODE_EXAMPLE})

    code: str = Field(
        max_length=16,
        description=(
            "The six-digit code from the verification email. Spaces and "
            "hyphens are ignored, so a pasted `123 456` is accepted."
        ),
        examples=[VERIFICATION_CODE_EXAMPLE],
    )

    @field_validator("code")
    @classmethod
    def _check_code(cls, value: str) -> str:
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) != VERIFICATION_CODE_DIGITS:
            raise ValueError(
                f"the verification code is {VERIFICATION_CODE_DIGITS} digits"
            )
        return digits


class ResendVerificationRequest(_EmailMixin):
    """Ask for another verification code.

    The response is the same whether or not the address has an account, and
    whether or not it is already verified.
    """

    model_config = examples({"email": EMAIL})


class PasswordResetRequest(_EmailMixin):
    """Begin a reset. The response is the same whether or not the account exists."""

    model_config = examples({"email": EMAIL})


class PasswordResetConfirmRequest(_EmailMixin):
    """Complete a reset with the emailed code and a new password.

    Both the address and the code are required: the code is six digits, so it
    is checked against one account rather than looked up across all of them
    (AUTH.md section 12).
    """

    model_config = examples(
        {
            "email": EMAIL,
            "code": VERIFICATION_CODE_EXAMPLE,
            "password": "a-different-passphrase-entirely",
        }
    )

    code: str = Field(
        max_length=16,
        description=(
            "The six-digit code from the reset email. Spaces and hyphens are "
            "ignored, so a pasted `123 456` is accepted."
        ),
        examples=[VERIFICATION_CODE_EXAMPLE],
    )
    password: Password = Field(
        description="The new password. At least 12 characters.",
    )

    @field_validator("code")
    @classmethod
    def _check_code(cls, value: str) -> str:
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) != VERIFICATION_CODE_DIGITS:
            raise ValueError(f"the reset code is {VERIFICATION_CODE_DIGITS} digits")
        return digits


class MfaVerifyRequest(_Request):
    """Complete an MFA login with a TOTP code or a recovery code."""

    model_config = examples(
        {"mfa_token": MFA_TOKEN_EXAMPLE, "code": "123456"},
        {"mfa_token": MFA_TOKEN_EXAMPLE, "code": "A1B2C-D3E4F"},
    )

    mfa_token: str = Field(max_length=2048)
    code: str = Field(
        max_length=32,
        description="Six-digit authenticator code, or one recovery code.",
    )


class MfaEnrolmentResponse(BaseModel):
    """A secret to enrol against. MFA is **not** active until confirmed."""

    model_config = response_examples(
        {
            "secret": "JBSWY3DPEHPK3PXP",
            "provisioning_uri": (
                "otpauth://totp/fundready:founder%40example.com"
                "?secret=JBSWY3DPEHPK3PXP&issuer=fundready&digits=6&period=30"
            ),
        }
    )

    secret: str = Field(description="Base32 TOTP secret, for manual entry.")
    provisioning_uri: str = Field(
        description="`otpauth://` URI to render as a QR code.",
    )


class MfaConfirmRequest(_Request):
    """Prove the authenticator holds the secret, then enable MFA."""

    model_config = examples({"code": "123456"})

    code: str = Field(max_length=32, description="Six-digit authenticator code.")


class MfaRecoveryCodesResponse(BaseModel):
    """Shown exactly once.

    The codes are stored hashed, so they cannot be shown again. Each works
    once, and using one is audit-logged.
    """

    model_config = response_examples(
        {
            "recovery_codes": [
                "A1B2C-D3E4F",
                "G5H6I-J7K8L",
                "M9N0O-P1Q2R",
                "S3T4U-V5W6X",
                "Y7Z8A-B9C0D",
                "E1F2G-H3I4J",
                "K5L6M-N7O8P",
                "Q9R0S-T1U2V",
                "W3X4Y-Z5A6B",
                "C7D8E-F9G0H",
            ]
        }
    )

    recovery_codes: list[str]


class ProvisionAdminRequest(_EmailMixin):
    """Create an admin account. Admin-only; there is no self-service path."""

    model_config = examples({"email": "ops@saci.example", "password": PASSWORD_EXAMPLE})

    password: Password = Field(
        description=(
            "Initial password, at least 12 characters. The new admin must "
            "verify their email and enrol MFA before any admin capability "
            "opens to them."
        ),
    )


class ChangeRoleRequest(_Request):
    """Move a user between roles."""

    model_config = examples({"role": "investor"})

    role: Role = Field(description="`founder`, `investor`, or `admin`.")
