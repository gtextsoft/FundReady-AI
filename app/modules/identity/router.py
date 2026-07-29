"""Identity HTTP endpoints.

Users, roles, account status, and session lifecycle (AUTH.md).

Layer: **router** (ARCHITECTURE.md section 3) -- HTTP only. Validate the request
with `schemas`, call exactly one `service` method, return a response schema.
No business logic, no database access, no LLM calls.
"""

from fastapi import APIRouter, status

from app.core.deps import AuthenticatedUserDep, SessionDep
from app.core.errors import UnauthenticatedError, error_responses
from app.modules.identity import service
from app.modules.identity.repository import UserRepository
from app.modules.identity.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    RegistrationAccepted,
    TokenPairResponse,
    UserResponse,
)

router = APIRouter(tags=["identity"])


@router.post(
    "/auth/register",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RegistrationAccepted,
    summary="Register a founder or investor",
    description=(
        "Creates an account with status `pending_verification`.\n\n"
        "**The response is identical whether or not the address was already "
        "registered.** That is deliberate -- a different response would let "
        "anyone test which addresses have accounts. Do not treat `202` as "
        "proof that a new account was created.\n\n"
        "`admin` is not an accepted role: admins are provisioned internally."
    ),
    responses=error_responses(403, 422),
)
async def register(
    payload: RegisterRequest, session: SessionDep
) -> RegistrationAccepted:
    await service.register_user(
        session, email=payload.email, password=payload.password, role=payload.role
    )
    return RegistrationAccepted()


@router.post(
    "/auth/login",
    response_model=TokenPairResponse,
    summary="Log in",
    description=(
        "Exchanges email and password for an access token and a refresh token.\n\n"
        "Every failure returns the same `401` with the same message -- whether "
        "the account does not exist, the password is wrong, or the account is "
        "temporarily locked after repeated failures. Do not branch on it.\n\n"
        "A `403` means the account is suspended. Logging in while "
        "`pending_verification` succeeds, but protected endpoints return `403` "
        "until the email is verified."
    ),
    responses=error_responses(401, 403, 422),
)
async def login(payload: LoginRequest, session: SessionDep) -> TokenPairResponse:
    user = await service.authenticate(
        session, email=payload.email, password=payload.password
    )
    pair = await service.issue_tokens(session, user)
    return TokenPairResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )


@router.post(
    "/auth/refresh",
    response_model=TokenPairResponse,
    summary="Exchange a refresh token for a new pair",
    description=(
        "Refresh tokens rotate: the presented token is consumed and a new pair "
        "returned. **Store the new refresh token immediately and discard the "
        "old one.**\n\n"
        "Presenting a refresh token that has already been used is treated as "
        "theft -- every token from that login is revoked and all access tokens "
        "are invalidated, so the user must log in again. Never retry a refresh "
        "with a token you have already exchanged."
    ),
    responses=error_responses(401, 403, 422),
)
async def refresh(payload: RefreshRequest, session: SessionDep) -> TokenPairResponse:
    pair = await service.refresh_tokens(session, payload.refresh_token)
    return TokenPairResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out",
    description=(
        "Revokes the presented refresh token and every token from the same "
        "login. The access token expires on its own shortly after.\n\n"
        "Always returns `204`, even for a token we do not recognise."
    ),
    responses=error_responses(422),
)
async def logout(payload: LogoutRequest, session: SessionDep) -> None:
    await service.logout(session, payload.refresh_token)


@router.get(
    "/users/me",
    response_model=UserResponse,
    summary="The caller's own account",
    description=(
        "Returns the authenticated user's own record and gate status.\n\n"
        "Reachable while `pending_verification`, so the client can prompt the "
        "user to verify their email. Use `kyc_status` and "
        "`subscription_status` to decide when to launch those flows."
    ),
    responses=error_responses(401, 403),
)
async def read_me(user: AuthenticatedUserDep, session: SessionDep) -> UserResponse:
    record = await UserRepository(session).get_by_id(user.id)
    if record is None:  # pragma: no cover - the token resolved a moment ago
        raise UnauthenticatedError
    return UserResponse.model_validate(record)
