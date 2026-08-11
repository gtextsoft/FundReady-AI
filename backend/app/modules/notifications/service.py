"""Notifications business logic (T1.2a + T5.3).

Layer: **service** (ARCHITECTURE.md section 3) -- business logic and
orchestration. Performs authorization and ownership checks (AUTH.md sections
5-6), calls this module's `repository`, and other modules' public service
functions only (never their internals).

Transactional email over Resend's HTTP API. Two rules shape everything here:

**Sending never raises into the caller.** Registration must return the same
`202` whether or not Resend is reachable. If a send failure propagated, an
email outage would become a registration outage -- and worse, it would create a
*timing and behaviour* difference between "address already existed" (no send)
and "address was new" (send attempted), reintroducing exactly the account
enumeration oracle that registration is written to avoid (AUTH.md section 3.2).

**The recipient's address never reaches a log line.** An email address is PII
(CLAUDE.md section 4), so failures record the provider's status and error
*type* -- never the response body, which typically echoes the address back.

Delivery prefers the Redis/RQ queue so a slow Resend does not hold an HTTP
request (T5.3). Tests and callers that inject an `httpx` client still send
inline. When Redis is unavailable the send falls back to the request thread
rather than dropping the message.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Final

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import CurrentUser
from app.modules.identity import service as identity
from app.modules.notifications.models import Notification
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import NotificationPage, NotificationResponse
from app.modules.notifications.templates import (
    EmailContent,
    audit_report_email,
    evidence_result_email,
    interest_update_email,
    kyc_verified_email,
    meeting_booked_email,
    password_reset_email,
    task_assigned_email,
    verification_email,
    welcome_email,
)

logger = logging.getLogger(__name__)

__all__ = [
    "create_notification",
    "dispatch_email",
    "list_notifications",
    "mark_notifications_read",
    "notify_evidence_result",
    "notify_interest_update",
    "notify_kyc_verified",
    "notify_meeting_booked",
    "notify_task_assigned",
    "send_audit_report_email",
    "send_email",
    "send_password_reset_email",
    "send_verification_email",
    "send_welcome_email",
]

RESEND_ENDPOINT: Final = "https://api.resend.com/emails"
SEND_TIMEOUT_SECONDS: Final = 10.0

KIND_TASK_ASSIGNED: Final = "task_assigned"
KIND_EVIDENCE_RESULT: Final = "evidence_result"
KIND_MEETING_BOOKED: Final = "meeting_booked"
KIND_INTEREST_UPDATE: Final = "interest_update"
KIND_KYC_VERIFIED: Final = "kyc_verified"


def _is_configured(settings: Settings) -> bool:
    key = settings.resend_api_key
    return bool(
        key is not None
        and key.get_secret_value().strip()
        and settings.email_from_address.strip()
    )


async def dispatch_email(
    to: str,
    content: EmailContent,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Queue the message when possible; otherwise send inline.

    An injected `client` always forces the inline path so unit tests keep
    driving Resend with a mock transport.
    """
    if client is not None:
        return await send_email(to, content, settings=settings, client=client)

    settings = settings or get_settings()
    try:
        from app.workers.queue import QueueUnavailableError, enqueue_email

        enqueue_email(to, content.subject, content.html, content.text)
        return True
    except Exception as error:
        from app.workers.queue import QueueUnavailableError

        if isinstance(error, QueueUnavailableError):
            return await send_email(to, content, settings=settings)
        logger.warning(
            "email enqueue failed; sending inline",
            extra={"context": {"reason": type(error).__name__}},
        )
        return await send_email(to, content, settings=settings)


async def send_email(
    to: str,
    content: EmailContent,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Send one message on the current thread. Returns provider acceptance.

    Never raises: a caller cannot be made to fail because email is down.
    Prefer `dispatch_email` from product code so delivery can leave the request.
    """
    settings = settings or get_settings()

    if not _is_configured(settings):
        # Development convenience: surface the link so local flows can be
        # completed without a provider account. The URL only -- never the
        # recipient -- so the no-PII-in-logs rule holds even here.
        if not settings.is_production:
            # No link here, deliberately. An earlier version logged the body so
            # local flows could be completed -- and `core.logging.RedactionFilter`
            # correctly scrubbed the `token=` out of it, because a verification
            # token *is* a credential. Rather than exempt ourselves from our own
            # control, local flows use `scripts/issue_dev_token.py`.
            logger.info(
                "email not configured; not sending",
                extra={"context": {"subject": content.subject}},
            )
            return False
        logger.error("email not configured; message dropped")
        return False

    key = settings.resend_api_key
    assert key is not None  # noqa: S101 - guaranteed by _is_configured
    payload: dict[str, Any] = {
        "from": settings.email_from_address,
        "to": [to],
        "subject": content.subject,
        "html": content.html,
        "text": content.text,
    }
    headers = {"Authorization": f"Bearer {key.get_secret_value()}"}

    try:
        if client is not None:
            response = await client.post(RESEND_ENDPOINT, json=payload, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=SEND_TIMEOUT_SECONDS) as owned:
                response = await owned.post(
                    RESEND_ENDPOINT, json=payload, headers=headers
                )
    except httpx.HTTPError as error:
        # Type only. The exception string can carry the request, and the
        # request carries the recipient.
        logger.warning(
            "email send failed",
            extra={"context": {"reason": type(error).__name__}},
        )
        return False

    if response.status_code >= httpx.codes.BAD_REQUEST:
        # Status only, deliberately not the body: provider errors quote the
        # address they rejected.
        logger.warning(
            "email rejected by provider",
            extra={"context": {"status": response.status_code}},
        )
        return False

    logger.info("email sent", extra={"context": {"subject": content.subject}})
    return True


async def send_verification_email(
    to: str, code: str, *, ttl_minutes: int, settings: Settings | None = None
) -> bool:
    """Email a new user the code that confirms their address (T1.2b calls this)."""
    return await dispatch_email(
        to, verification_email(code, ttl_minutes), settings=settings
    )


async def send_password_reset_email(
    to: str, code: str, *, ttl_minutes: int, settings: Settings | None = None
) -> bool:
    """Email a six-digit password-reset code (AUTH.md section 12)."""
    return await dispatch_email(
        to, password_reset_email(code, ttl_minutes), settings=settings
    )


async def send_welcome_email(to: str, *, settings: Settings | None = None) -> bool:
    """Greet an account whose address has just been confirmed."""
    return await dispatch_email(to, welcome_email(), settings=settings)


async def send_audit_report_email(
    to: str, report: Any, app_url: str, *, settings: Settings | None = None
) -> bool:
    """Email a finished audit to the founder it belongs to.

    `report` is the assembled founder-tier report. It is untyped here because
    `notifications` sits below `audit` in the layer order and must not import
    from it -- see the note on `audit_report_email`.
    """
    return await dispatch_email(
        to, audit_report_email(report, app_url), settings=settings
    )


# ---------------------------------------------------------------------------
# In-app notifications
# ---------------------------------------------------------------------------


async def create_notification(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    kind: str,
    title: str,
    body: str,
    payload: dict[str, Any] | None = None,
) -> Notification:
    """Persist one inbox row. Other modules call this for product events."""
    return await NotificationRepository(session).create(
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        payload=payload,
    )


async def list_notifications(
    session: AsyncSession,
    actor: CurrentUser,
    *,
    limit: int = 50,
    offset: int = 0,
) -> NotificationPage:
    """The caller's inbox, newest first."""
    rows, total = await NotificationRepository(session).list_for_user(
        actor.id, limit=limit, offset=offset
    )
    return NotificationPage(
        items=[NotificationResponse.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


async def mark_notifications_read(
    session: AsyncSession,
    actor: CurrentUser,
    ids: list[uuid.UUID],
) -> int:
    """Mark the caller's notifications read. Foreign ids are ignored."""
    return await NotificationRepository(session).mark_read(actor.id, ids)


async def _email_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    content: EmailContent,
    *,
    settings: Settings | None = None,
) -> bool:
    """Resolve the mailbox and dispatch. Missing users are a quiet no-op."""
    to = await identity.get_user_email(session, user_id)
    if to is None:
        return False
    return await dispatch_email(to, content, settings=settings)


async def notify_task_assigned(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    task_summary: str,
    app_url: str,
    payload: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> Notification:
    """Inbox + email when a readiness task is raised."""
    row = await create_notification(
        session,
        user_id=user_id,
        kind=KIND_TASK_ASSIGNED,
        title="New readiness task",
        body=task_summary,
        payload=payload,
    )
    await _email_user(
        session,
        user_id,
        task_assigned_email(task_summary, app_url),
        settings=settings,
    )
    return row


async def notify_evidence_result(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    outcome: str,
    app_url: str,
    payload: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> Notification:
    """Inbox + email when evidence assessment finishes."""
    row = await create_notification(
        session,
        user_id=user_id,
        kind=KIND_EVIDENCE_RESULT,
        title="Evidence assessment result",
        body=f"Your evidence was assessed as {outcome}.",
        payload=payload,
    )
    await _email_user(
        session,
        user_id,
        evidence_result_email(outcome, app_url),
        settings=settings,
    )
    return row


async def notify_meeting_booked(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    when_label: str,
    app_url: str,
    payload: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> Notification:
    """Inbox + email when SACI books a meeting."""
    row = await create_notification(
        session,
        user_id=user_id,
        kind=KIND_MEETING_BOOKED,
        title="Meeting booked",
        body=f"A meeting has been scheduled for {when_label}.",
        payload=payload,
    )
    await _email_user(
        session,
        user_id,
        meeting_booked_email(when_label, app_url),
        settings=settings,
    )
    return row


async def notify_interest_update(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    status: str,
    app_url: str,
    payload: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> Notification:
    """Inbox + email when an interest expression changes state."""
    row = await create_notification(
        session,
        user_id=user_id,
        kind=KIND_INTEREST_UPDATE,
        title="Interest update",
        body=f"An introduction request is now {status}.",
        payload=payload,
    )
    await _email_user(
        session,
        user_id,
        interest_update_email(status, app_url),
        settings=settings,
    )
    return row


async def notify_kyc_verified(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    app_url: str,
    payload: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> Notification:
    """Inbox + email when investor KYC succeeds."""
    row = await create_notification(
        session,
        user_id=user_id,
        kind=KIND_KYC_VERIFIED,
        title="Identity verified",
        body="Your identity check is complete. You can browse dealflow.",
        payload=payload,
    )
    await _email_user(session, user_id, kyc_verified_email(app_url), settings=settings)
    return row
