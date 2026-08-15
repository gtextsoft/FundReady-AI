"""Identity HTTP endpoints.

Users, roles, account status, and session lifecycle (AUTH.md).

Layer: **router** (ARCHITECTURE.md section 3) -- HTTP only. Validate the request
with `schemas`, call exactly one `service` method, return a response schema.
No business logic, no database access, no LLM calls.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import AuthenticatedUserDep, CurrentAdmin, SessionDep
from app.core.errors import UnauthenticatedError, error_responses
from app.core.security import AccountStatus, Role, create_mfa_challenge_token
from app.modules.identity import service
from app.modules.identity.repository import UserRepository
from app.modules.identity.schemas import (
    ChangeRoleRequest,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    MfaConfirmRequest,
    MfaEnrolmentResponse,
    MfaRecoveryCodesResponse,
    MfaVerifyRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    ProvisionAdminRequest,
    RefreshRequest,
    RegisterRequest,
    RegistrationAccepted,
    ResendVerificationRequest,
    TokenPairResponse,
    UserPage,
    UserResponse,
    VerifyEmailRequest,
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
        "**Founders must register with a company email address.** A consumer "
        "mailbox (`gmail.com`, `outlook.com`, `yahoo.com`, ...) is refused "
        'with `422` and `details.reason = "consumer_email_domain"` -- show '
        "that against the email field. Investors are not restricted. The "
        "domain also becomes the starting company name on the startup "
        "profile, so this rejection is explicit rather than uniform: there is "
        "no account to enumerate, only the domain the caller just typed.\n\n"
        "`admin` is not an accepted role: admins are provisioned internally."
    ),
    responses=error_responses(403, 422),
)
async def register(
    payload: RegisterRequest, session: SessionDep
) -> RegistrationAccepted:
    await service.register_user(
        session,
        email=payload.email,
        password=payload.password,
        role=payload.role,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    return RegistrationAccepted()


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    summary="Log in",
    description=(
        "Exchanges email and password for tokens.\n\n"
        "**Branch on `status`.** `authenticated` returns `tokens`. "
        "`mfa_required` means the password was correct but a second factor is "
        "outstanding: send the returned `mfa_token` and the code to "
        "`POST /v1/auth/mfa/verify`. The `mfa_token` grants nothing by "
        "itself and expires in 5 minutes.\n\n"
        "Every failure returns the same `401` with the same message -- whether "
        "the account does not exist, the password is wrong, or the account is "
        "temporarily locked after repeated failures. Do not branch on it.\n\n"
        "A `403` means the account is suspended. Logging in while "
        "`pending_verification` succeeds, but protected endpoints return `403` "
        "until the email is verified."
    ),
    responses=error_responses(401, 403, 422),
)
async def login(payload: LoginRequest, session: SessionDep) -> LoginResponse:
    user = await service.authenticate(
        session, email=payload.email, password=payload.password
    )
    if user.mfa_enabled:
        return LoginResponse(
            status="mfa_required",
            mfa_token=create_mfa_challenge_token(user.id),
        )
    pair = await service.issue_tokens(session, user)
    return LoginResponse(
        status="authenticated",
        tokens=TokenPairResponse(
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            expires_in=pair.expires_in,
        ),
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
    return UserResponse.of(record)


@router.post(
    "/auth/verify-email",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Confirm an email address",
    description=(
        "Confirms the address and activates the account.\n\n"
        "**Collect the six-digit code from the verification email**, together "
        "with the address it was sent to -- both are required, because a "
        "six-digit code is only checked against the one account it belongs "
        "to. Spaces and hyphens in the code are ignored.\n\n"
        "`422` covers a wrong code, an expired one, one already used, one "
        "whose attempts are exhausted, and an address with no account at all "
        "-- one message for every case, so do not try to distinguish them, and "
        "do not treat the error as evidence that an account exists.\n\n"
        f"**The code expires in {int(service.VERIFICATION_TTL.total_seconds() // 60)} "
        f"minutes and allows {service.MAX_VERIFICATION_ATTEMPTS} attempts.** "
        "After that it is dead and the user needs a new one from "
        "`POST /v1/auth/verify-email/resend`. Requesting a new code "
        "invalidates the previous one, so always verify against the newest "
        "email."
    ),
    responses=error_responses(422),
)
async def verify_email(payload: VerifyEmailRequest, session: SessionDep) -> None:
    await service.verify_email(session, email=payload.email, code=payload.code)


@router.post(
    "/auth/verify-email/resend",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RegistrationAccepted,
    summary="Send another verification code",
    description=(
        "Issues a fresh code and emails it, **invalidating the previous "
        "one**.\n\n"
        "**Always returns `202` with the same body** -- whether the address "
        "has no account, is already verified, or simply asked again too soon. "
        "Nothing here can be used to discover who has an account or who has "
        "finished verifying.\n\n"
        "A code requested within "
        f"{int(service.VERIFICATION_RESEND_COOLDOWN.total_seconds())} seconds "
        "of the last one is not sent, so do not offer the button as an instant "
        "retry -- put a short countdown on it."
    ),
    responses=error_responses(422),
)
async def resend_verification_email(
    payload: ResendVerificationRequest, session: SessionDep
) -> RegistrationAccepted:
    await service.resend_verification_email(session, payload.email)
    return RegistrationAccepted(
        message="If that address needs verifying, a new code is on its way.",
    )


@router.post(
    "/auth/password-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RegistrationAccepted,
    summary="Begin a password reset",
    description=(
        "Emails a six-digit reset code if the address has an account.\n\n"
        "**Always returns `202` with the same body**, whether or not the "
        "address is registered, so this cannot be used to discover accounts.\n\n"
        f"**The code expires in "
        f"{int(service.PASSWORD_RESET_TTL.total_seconds() // 60)} "
        f"minutes and allows {service.MAX_VERIFICATION_ATTEMPTS} attempts.** "
        "Requesting another code invalidates the previous one. A request within "
        f"{int(service.VERIFICATION_RESEND_COOLDOWN.total_seconds())} seconds "
        "of the last one is not sent — put a short countdown on the button."
    ),
    responses=error_responses(422),
)
async def request_password_reset(
    payload: PasswordResetRequest, session: SessionDep
) -> RegistrationAccepted:
    await service.request_password_reset(session, payload.email)
    return RegistrationAccepted(
        status="pending_verification",
        message="If that address has an account, a reset code is on its way.",
    )


@router.post(
    "/auth/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Complete a password reset",
    description=(
        "Sets the new password with the emailed six-digit code and **ends every "
        "existing session**: all refresh tokens are revoked and every access "
        "token already issued stops working. The user must log in again "
        "afterwards, on every device.\n\n"
        "**Collect the code from the reset email together with the address it "
        "was sent to** — both are required, because a six-digit code is only "
        "checked against the one account it belongs to. Spaces and hyphens in "
        "the code are ignored.\n\n"
        "`422` covers a wrong code, an expired one, one already used, one "
        "whose attempts are exhausted, and an address with no account at all "
        "-- one message for every case.\n\n"
        "Any other reset code already sent to that address is invalidated too."
    ),
    responses=error_responses(422),
)
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest, session: SessionDep
) -> None:
    await service.reset_password(
        session,
        email=payload.email,
        code=payload.code,
        new_password=payload.password,
    )


@router.post(
    "/auth/mfa/verify",
    response_model=TokenPairResponse,
    summary="Complete an MFA login",
    description=(
        "Exchanges the `mfa_token` from login, plus a six-digit authenticator "
        "code **or** one recovery code, for a token pair.\n\n"
        "A code is accepted once: replaying the same authenticator code inside "
        "its own 30-second window is refused, and a recovery code is spent "
        "permanently. Every failure returns the same `401`."
    ),
    responses=error_responses(401, 403, 422),
)
async def verify_mfa(
    payload: MfaVerifyRequest, session: SessionDep
) -> TokenPairResponse:
    pair = await service.verify_mfa_challenge(session, payload.mfa_token, payload.code)
    return TokenPairResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )


@router.post(
    "/auth/mfa/enroll",
    response_model=MfaEnrolmentResponse,
    summary="Begin MFA enrolment",
    description=(
        "Issues a TOTP secret to add to an authenticator app. **MFA is not "
        "active yet** -- call `/v1/auth/mfa/confirm` with a code to enable it, "
        "which proves the app really holds the secret before the account starts "
        "depending on it.\n\n"
        "Calling this again replaces an unconfirmed secret. Required for admin "
        "accounts, optional for everyone else."
    ),
    responses=error_responses(401, 403),
)
async def enroll_mfa(
    user: AuthenticatedUserDep, session: SessionDep
) -> MfaEnrolmentResponse:
    record = await UserRepository(session).get_by_id(user.id)
    if record is None:  # pragma: no cover - the token resolved a moment ago
        raise UnauthenticatedError
    enrolment = await service.start_mfa_enrolment(session, record)
    return MfaEnrolmentResponse(
        secret=enrolment.secret, provisioning_uri=enrolment.provisioning_uri
    )


@router.post(
    "/auth/mfa/confirm",
    response_model=MfaRecoveryCodesResponse,
    summary="Confirm MFA enrolment",
    description=(
        "Enables MFA and returns ten recovery codes.\n\n"
        "**Show them once and tell the user to store them.** They are held "
        "hashed and cannot be shown again. Each works once; using one is "
        "audit-logged. Re-enrolling invalidates the previous set."
    ),
    responses=error_responses(401, 403, 422),
)
async def confirm_mfa(
    payload: MfaConfirmRequest, user: AuthenticatedUserDep, session: SessionDep
) -> MfaRecoveryCodesResponse:
    record = await UserRepository(session).get_by_id(user.id)
    if record is None:  # pragma: no cover
        raise UnauthenticatedError
    codes = await service.confirm_mfa_enrolment(session, record, payload.code)
    return MfaRecoveryCodesResponse(recovery_codes=codes)


# ---------------------------------------------------------------------------
# Admin user management. Every route here is admin-only, and `CurrentAdmin`
# additionally refuses an admin who has not enrolled MFA (AUTH.md section 9),
# so none of this is reachable without a second factor.
# ---------------------------------------------------------------------------

ADMIN_ACTION_DESCRIPTION = (
    "\n\nRequires an admin account **with MFA enrolled**. An admin who has "
    "not enrolled receives `403` here until they do."
)


@router.get(
    "/admin/users",
    response_model=UserPage,
    summary="List accounts",
    description=(
        "Every user, newest first. Filter with `role`, `status`, and `q` "
        "(email or name)."
        + ADMIN_ACTION_DESCRIPTION
    ),
    responses=error_responses(401, 403, 422),
)
async def list_users(
    actor: CurrentAdmin,
    session: SessionDep,
    role: Annotated[Role | None, Query()] = None,
    account_status: Annotated[AccountStatus | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserPage:
    rows, total = await service.list_users(
        session,
        actor,
        role=role,
        status=account_status,
        q=q,
        limit=limit,
        offset=offset,
    )
    return UserPage(
        items=[UserResponse.of(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/admin/users",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
    summary="Provision an admin account",
    description=(
        "Creates an admin. This is the only way one comes into existence -- "
        "`/v1/auth/register` refuses the role.\n\n"
        "The new admin lands `pending_verification` and without MFA, so they "
        "must verify their address and enrol a second factor before any admin "
        "capability opens to them. A verification email is sent.\n\n"
        "Unlike self-registration, a duplicate address returns `409` rather "
        "than a uniform success: the caller is already trusted, so there is no "
        "enumeration concern." + ADMIN_ACTION_DESCRIPTION
    ),
    responses=error_responses(401, 403, 409, 422),
)
async def provision_admin(
    payload: ProvisionAdminRequest, actor: CurrentAdmin, session: SessionDep
) -> UserResponse:
    admin = await service.provision_admin(
        session, actor, email=payload.email, password=payload.password
    )
    return UserResponse.of(admin)


@router.post(
    "/admin/users/{user_id}/suspend",
    response_model=UserResponse,
    summary="Suspend an account",
    description=(
        "Blocks the account and **ends its sessions immediately** -- refresh "
        "tokens revoked, access tokens already issued invalidated.\n\n"
        "`403` if you target your own account. `409` if the target is the only "
        "active admin, since the only way back from zero admins is database "
        "credentials." + ADMIN_ACTION_DESCRIPTION
    ),
    responses=error_responses(401, 403, 404, 409, 422),
)
async def suspend_user(
    user_id: uuid.UUID, actor: CurrentAdmin, session: SessionDep
) -> UserResponse:
    return UserResponse.of(await service.suspend_user(session, actor, user_id))


@router.post(
    "/admin/users/{user_id}/reactivate",
    response_model=UserResponse,
    summary="Lift a suspension",
    description=(
        "Returns the account to `active`, or to `pending_verification` if the "
        "address was never verified -- reactivating does not confer "
        "verification.\n\n"
        "`409` if the account is not suspended." + ADMIN_ACTION_DESCRIPTION
    ),
    responses=error_responses(401, 403, 404, 409, 422),
)
async def reactivate_user(
    user_id: uuid.UUID, actor: CurrentAdmin, session: SessionDep
) -> UserResponse:
    return UserResponse.of(await service.reactivate_user(session, actor, user_id))


@router.patch(
    "/admin/users/{user_id}/role",
    response_model=UserResponse,
    summary="Change a user's role",
    description=(
        "Applies the new role and **forces the user to log in again**: "
        "`session_valid_after` moves, so their existing access and refresh "
        "tokens stop working and the next login is authorised against the new "
        "role.\n\n"
        "`403` if you target your own account. `409` if the user already has "
        "that role, or if demoting them would leave no active admin."
        + ADMIN_ACTION_DESCRIPTION
    ),
    responses=error_responses(401, 403, 404, 409, 422),
)
async def change_user_role(
    user_id: uuid.UUID,
    payload: ChangeRoleRequest,
    actor: CurrentAdmin,
    session: SessionDep,
) -> UserResponse:
    return UserResponse.of(
        await service.change_user_role(session, actor, user_id, payload.role)
    )
