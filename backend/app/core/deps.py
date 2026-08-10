"""Shared FastAPI dependencies.

Composes `config`, `db`, and `security` into the annotated dependencies routers
declare. Routers depend on the aliases here rather than reaching into those
modules directly, so a change to how a session or a current user is obtained is
a one-line change in one place.

Authorization is layered (AUTH.md section 5): authenticated, then account
status, then role, then condition, then ownership, then tier. The first three
live here. **Ownership is checked in the service layer** -- it is the primary
tenant-isolation wall (DECISIONS.md D13) and cannot be expressed as a
route-level dependency, because only the service knows which object is being
reached for.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.db import AsyncSession, get_session
from app.core.entitlement import has_founder_access, is_paid
from app.core.errors import ForbiddenError, UnauthenticatedError
from app.core.security import (
    AccountStatus,
    CurrentUser,
    Role,
    resolve_current_user,
)

SettingsDep = Annotated[Settings, Depends(get_settings)]
"""Process-wide settings."""

SessionDep = Annotated[AsyncSession, Depends(get_session)]
"""A transactional database session, committed on success, rolled back on error."""

# `auto_error=False` so a missing or malformed header raises *our*
# `UnauthenticatedError` and comes back in the documented error envelope,
# rather than FastAPI's own untyped 403.
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="Bearer",
    description="Access token issued by `POST /v1/auth/login`.",
)

BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
]


async def get_authenticated_user(credentials: BearerCredentials) -> CurrentUser:
    """The caller behind a valid token, whatever their account status.

    Only `/v1/users/me` should use this. Everything else wants
    `get_current_user`, which additionally requires an active account -- an
    unverified user must be able to *see* that they are unverified, and nothing
    more.
    """
    if credentials is None or not credentials.credentials.strip():
        raise UnauthenticatedError
    return await resolve_current_user(credentials.credentials)


AuthenticatedUserDep = Annotated[CurrentUser, Depends(get_authenticated_user)]
"""An authenticated caller, possibly still pending email verification."""


async def get_current_user(user: AuthenticatedUserDep) -> CurrentUser:
    """An authenticated caller with an active account -- the normal case."""
    if user.status is not AccountStatus.ACTIVE:
        raise ForbiddenError("Verify your email address to continue.")
    return user


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
"""Any authenticated, active user."""


def require_role(*roles: Role) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    """Restrict an endpoint to the given roles.

    Denials are `403` -- the caller is authenticated, just not permitted, so
    the mobile client must not retry after refreshing (AUTH.md section 4.3).

    Admins additionally need MFA enrolled (AUTH.md section 9). This resolves the
    bootstrap circle -- enrolling requires being logged in -- by letting an
    unenrolled admin hold a token that can reach the enrolment endpoints and
    nothing else. No admin capability is ever exercised without a second factor.
    """
    allowed = frozenset(roles)

    async def dependency(user: CurrentUserDep) -> CurrentUser:
        if user.role not in allowed:
            raise ForbiddenError
        if user.role is Role.ADMIN and not user.mfa_enabled:
            raise ForbiddenError(
                "Admin accounts must enrol in two-factor authentication first."
            )
        return user

    return dependency


# Single-role aliases for the common cases. Where the permission matrix allows
# an admin to act on a founder's or investor's behalf, compose explicitly --
# `require_role(Role.FOUNDER, Role.ADMIN)` -- rather than widening these.
CurrentFounder = Annotated[CurrentUser, Depends(require_role(Role.FOUNDER))]
CurrentInvestor = Annotated[CurrentUser, Depends(require_role(Role.INVESTOR))]
CurrentAdmin = Annotated[CurrentUser, Depends(require_role(Role.ADMIN))]


async def require_active_subscription(user: CurrentFounder) -> CurrentUser:
    """Founder with a Stripe-granted unlock (AUTH.md section 8, D21).

    Trial access is *not* enough here — use `require_founder_access` for
    capabilities that stay open during the trial window.
    """
    if not is_paid(user.subscription_status):
        raise ForbiddenError(
            "Unlock SACI FundMe to continue.",
            {"reason": "payment_required"},
        )
    return user


async def require_founder_access(user: CurrentUserDep) -> CurrentUser:
    """Trial or paid unlock for founders; admins (MFA) pass through.

    Used on expensive or marketplace-facing founder writes (audit, publish,
    evidence). Investors are refused.
    """
    if user.role is Role.ADMIN:
        if not user.mfa_enabled:
            raise ForbiddenError(
                "Admin accounts must enrol in two-factor authentication first."
            )
        return user
    if user.role is not Role.FOUNDER:
        raise ForbiddenError
    if user.created_at is None or not has_founder_access(
        subscription_status=user.subscription_status,
        created_at=user.created_at,
    ):
        raise ForbiddenError(
            "Your free trial has ended. Unlock SACI FundMe to continue.",
            {"reason": "payment_required"},
        )
    return user


FounderWithAccess = Annotated[CurrentUser, Depends(require_founder_access)]
"""Founder with trial or paid unlock (admins with MFA also allowed)."""

PaidFounder = Annotated[CurrentUser, Depends(require_active_subscription)]
"""Founder with a completed Stripe unlock only."""

__all__ = [
    "AuthenticatedUserDep",
    "CurrentAdmin",
    "CurrentFounder",
    "CurrentInvestor",
    "CurrentUserDep",
    "FounderWithAccess",
    "PaidFounder",
    "SessionDep",
    "SettingsDep",
    "bearer_scheme",
    "get_authenticated_user",
    "get_current_user",
    "require_active_subscription",
    "require_founder_access",
    "require_role",
]
