"""Commerce business logic: Checkout + verified Stripe webhooks.

Layer: **service** (ARCHITECTURE.md section 3). Entitlement is granted only
from verified webhooks (CLAUDE.md section 4, DECISIONS.md D21) — never from a
client-reported payment state.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import (
    ConfigurationError,
    ForbiddenError,
    InvalidRequestError,
    NotFoundError,
)
from app.core.security import CurrentUser, Role, SubscriptionStatus
from app.modules.commerce.models import Purchase, PurchaseKind, PurchaseStatus
from app.modules.commerce.repository import (
    PurchaseRepository,
    StripeWebhookEventRepository,
)
from app.modules.commerce.schemas import CheckoutSessionResponse, UnlockReceiptResponse
from app.modules.identity.models import AuditAction
from app.modules.identity.repository import UserRepository
from app.modules.identity.service import record_action

logger = logging.getLogger(__name__)

UNLOCK_METADATA_KIND = "unlock"


def _configure_stripe(settings: Settings) -> None:
    key = settings.stripe_secret_key
    if key is None or not key.get_secret_value().strip():
        raise ConfigurationError
    stripe.api_key = key.get_secret_value()


async def create_unlock_checkout(
    session: AsyncSession,
    actor: CurrentUser,
    *,
    settings: Settings | None = None,
) -> CheckoutSessionResponse:
    """Create a Stripe Checkout Session for the one-off founder unlock."""
    if actor.role is not Role.FOUNDER:
        raise ForbiddenError("Only founders can purchase an unlock.")

    settings = settings or get_settings()
    price_id = settings.stripe_price_id_unlock.strip()
    if not price_id:
        raise ConfigurationError

    users = UserRepository(session)
    user = await users.get_by_id(actor.id)
    if user is None:
        raise NotFoundError

    if user.subscription_status is SubscriptionStatus.ACTIVE:
        raise ConflictAlreadyUnlockedError()

    _configure_stripe(settings)
    success = (
        settings.stripe_checkout_success_url.strip()
        or f"{settings.app_link_base_url.rstrip('/')}/founder/paywall?checkout=success"
    )
    cancel = (
        settings.stripe_checkout_cancel_url.strip()
        or f"{settings.app_link_base_url.rstrip('/')}/founder/paywall?checkout=cancel"
    )

    create_kwargs: dict[str, Any] = {
        "mode": "payment",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success,
        "cancel_url": cancel,
        "client_reference_id": str(user.id),
        "metadata": {
            "user_id": str(user.id),
            "kind": UNLOCK_METADATA_KIND,
        },
        "payment_intent_data": {
            "metadata": {
                "user_id": str(user.id),
                "kind": UNLOCK_METADATA_KIND,
            }
        },
    }
    if user.stripe_customer_id:
        create_kwargs["customer"] = user.stripe_customer_id
    else:
        create_kwargs["customer_email"] = user.email
        create_kwargs["customer_creation"] = "always"

    checkout = stripe.checkout.Session.create(**create_kwargs)
    session_id = str(checkout.id)
    url = checkout.url
    if not url:
        raise ConfigurationError

    amount = int(checkout.amount_total or 0)
    currency = str(checkout.currency or "usd").upper()
    await PurchaseRepository(session).add(
        Purchase(
            user_id=user.id,
            kind=PurchaseKind.UNLOCK,
            status=PurchaseStatus.PENDING,
            amount_minor=amount,
            currency=currency,
            stripe_checkout_session_id=session_id,
        )
    )

    customer_id = checkout.customer
    if customer_id and not user.stripe_customer_id:
        user.stripe_customer_id = str(customer_id)
        await session.flush()

    return CheckoutSessionResponse(checkout_url=url, session_id=session_id)


class ConflictAlreadyUnlockedError(InvalidRequestError):
    """Founder already holds an active unlock."""

    def __init__(self) -> None:
        super().__init__(
            "This account is already unlocked.",
            {"reason": "already_unlocked"},
        )


async def get_unlock_receipt(
    session: AsyncSession, actor: CurrentUser
) -> UnlockReceiptResponse:
    """The founder's completed unlock, if any."""
    if actor.role is not Role.FOUNDER:
        raise ForbiddenError
    purchase = await PurchaseRepository(session).latest_completed_unlock(actor.id)
    if purchase is None or purchase.completed_at is None:
        raise NotFoundError
    return UnlockReceiptResponse(
        reference=str(purchase.id),
        amount=purchase.amount_minor,
        currency=purchase.currency,
        paid_at=purchase.completed_at,
    )


async def handle_stripe_webhook(
    session: AsyncSession,
    *,
    payload: bytes,
    signature: str,
    settings: Settings | None = None,
) -> dict[str, str]:
    """Verify and process one Stripe webhook delivery.

    Signature verification is mandatory. Unknown or unhandled event types are
    acknowledged (200) after idempotent recording so Stripe stops retrying.
    """
    settings = settings or get_settings()
    secret = settings.stripe_webhook_secret
    if secret is None or not secret.get_secret_value().strip():
        raise ConfigurationError

    try:
        # Stripe's stub marks construct_event as untyped.
        event = stripe.Webhook.construct_event(  # type: ignore[no-untyped-call]
            payload,
            signature,
            secret.get_secret_value(),
        )
    except (ValueError, stripe.SignatureVerificationError) as error:
        logger.warning(
            "stripe webhook rejected",
            extra={"context": {"reason": type(error).__name__}},
        )
        raise InvalidRequestError(
            "Invalid Stripe webhook signature.",
            {"reason": "invalid_signature"},
        ) from None

    event_id = str(event["id"])
    event_type = str(event["type"])
    events = StripeWebhookEventRepository(session)
    if await events.get(event_id) is not None:
        return {"status": "duplicate"}

    if event_type == "checkout.session.completed":
        await _apply_checkout_completed(session, event["data"]["object"])
    # Future: invoice.* / customer.subscription.* if Billing is adopted (D21).

    await events.record(event_id, event_type)
    return {"status": "ok"}


async def _apply_checkout_completed(
    session: AsyncSession, checkout: dict[str, Any]
) -> None:
    metadata = checkout.get("metadata") or {}
    if metadata.get("kind") != UNLOCK_METADATA_KIND:
        logger.info(
            "stripe checkout ignored",
            extra={"context": {"reason": "unknown_kind"}},
        )
        return

    user_id_raw = metadata.get("user_id") or checkout.get("client_reference_id")
    if not user_id_raw:
        logger.warning("stripe checkout missing user_id")
        return

    try:
        user_id = uuid.UUID(str(user_id_raw))
    except ValueError:
        logger.warning("stripe checkout bad user_id")
        return

    users = UserRepository(session)
    user = await users.get_by_id(user_id)
    if user is None:
        logger.warning("stripe checkout user missing")
        return

    session_id = str(checkout["id"])
    purchases = PurchaseRepository(session)
    purchase = await purchases.get_by_session_id(session_id)
    amount = int(checkout.get("amount_total") or 0)
    currency = str(checkout.get("currency") or "usd").upper()
    payment_intent = checkout.get("payment_intent")
    payment_intent_id = str(payment_intent) if payment_intent else None

    if purchase is None:
        purchase = await purchases.add(
            Purchase(
                user_id=user.id,
                kind=PurchaseKind.UNLOCK,
                status=PurchaseStatus.PENDING,
                amount_minor=amount,
                currency=currency,
                stripe_checkout_session_id=session_id,
            )
        )

    if purchase.status is not PurchaseStatus.COMPLETED:
        await purchases.mark_completed(
            purchase,
            payment_intent_id=payment_intent_id,
            amount_minor=amount,
            currency=currency,
        )

    customer = checkout.get("customer")
    if customer and not user.stripe_customer_id:
        user.stripe_customer_id = str(customer)

    previous = user.subscription_status
    user.subscription_status = SubscriptionStatus.ACTIVE
    await session.flush()

    await record_action(
        session,
        AuditAction.PURCHASE_COMPLETED,
        actor_id=None,
        target_type="purchase",
        target_id=str(purchase.id),
        details={"kind": PurchaseKind.UNLOCK.value, "user_id": str(user.id)},
    )
    if previous is not SubscriptionStatus.ACTIVE:
        await record_action(
            session,
            AuditAction.SUBSCRIPTION_CHANGED,
            actor_id=None,
            target_type="user",
            target_id=str(user.id),
            details={
                "from": previous.value,
                "to": SubscriptionStatus.ACTIVE.value,
                "source": "stripe_webhook",
                "at": datetime.now(UTC).isoformat(),
            },
        )
