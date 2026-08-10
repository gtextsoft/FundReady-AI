"""Notifications business logic.

Layer: **service** (ARCHITECTURE.md section 3) -- business logic and
orchestration. Performs authorization and ownership checks (AUTH.md sections
5-6), calls this module's `repository`, `app.ai`, and other modules' public
service functions only (never their internals). Enqueues background jobs.
Selects the tier serializer for every response carrying report data
(DECISIONS.md D8).

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

Delivery is synchronous for now. Moving it onto the queue belongs with T2.8/T5.3;
the timeout below is what keeps that from being urgent.
"""

import logging
from typing import Any, Final

import httpx

from app.core.config import Settings, get_settings
from app.modules.notifications.templates import (
    EmailContent,
    audit_report_email,
    password_reset_email,
    verification_email,
    welcome_email,
)

logger = logging.getLogger(__name__)

RESEND_ENDPOINT: Final = "https://api.resend.com/emails"
SEND_TIMEOUT_SECONDS: Final = 10.0


def _is_configured(settings: Settings) -> bool:
    key = settings.resend_api_key
    return bool(
        key is not None
        and key.get_secret_value().strip()
        and settings.email_from_address.strip()
    )


async def send_email(
    to: str,
    content: EmailContent,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Send one message. Returns whether the provider accepted it.

    Never raises: a caller cannot be made to fail because email is down.
    `client` is injectable so tests can drive this without a network, and so a
    pooled client can be shared later.
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
    return await send_email(
        to, verification_email(code, ttl_minutes), settings=settings
    )


async def send_password_reset_email(
    to: str, reset_url: str, *, settings: Settings | None = None
) -> bool:
    """Send a single-use password reset link (T1.2b calls this)."""
    return await send_email(to, password_reset_email(reset_url), settings=settings)


async def send_welcome_email(to: str, *, settings: Settings | None = None) -> bool:
    """Greet an account whose address has just been confirmed."""
    return await send_email(to, welcome_email(), settings=settings)


async def send_audit_report_email(
    to: str, report: Any, app_url: str, *, settings: Settings | None = None
) -> bool:
    """Email a finished audit to the founder it belongs to.

    `report` is the assembled founder-tier report. It is untyped here because
    `notifications` sits below `audit` in the layer order and must not import
    from it -- see the note on `audit_report_email`.
    """
    return await send_email(to, audit_report_email(report, app_url), settings=settings)
