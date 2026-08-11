"""Commerce business logic: Checkout + verified Stripe webhooks + catalogue.

Layer: **service** (ARCHITECTURE.md section 3). Entitlement is granted only
from verified webhooks (CLAUDE.md section 4, DECISIONS.md D21) — never from a
client-reported payment state. Catalogue enrolment for paid products follows
the same rule (T3.2 / D18).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.entitlement import has_founder_access
from app.core.errors import (
    ConfigurationError,
    ConflictError,
    ForbiddenError,
    InvalidRequestError,
    NotFoundError,
)
from app.core.security import CurrentUser, Role, SubscriptionStatus, assert_admin
from app.modules.commerce.models import (
    Product,
    ProductEnrolment,
    ProductKind,
    Purchase,
    PurchaseKind,
    PurchaseStatus,
)
from app.modules.commerce.repository import (
    ProductEnrolmentRepository,
    ProductRepository,
    PurchaseRepository,
    StripeWebhookEventRepository,
)
from app.modules.commerce.schemas import (
    CheckoutSessionResponse,
    EnrolmentResponse,
    ProductCreate,
    ProductEnrolResult,
    ProductPage,
    ProductResponse,
    ProductUpdate,
    UnlockReceiptResponse,
)
from app.modules.identity.models import AuditAction
from app.modules.identity.repository import UserRepository
from app.modules.identity.service import record_action

logger = logging.getLogger(__name__)

UNLOCK_METADATA_KIND = "unlock"
PRODUCT_METADATA_KIND = "product"


def _configure_stripe(settings: Settings) -> None:
    key = settings.stripe_secret_key
    if key is None or not key.get_secret_value().strip():
        raise ConfigurationError
    stripe.api_key = key.get_secret_value()


def _require_founder_access(actor: CurrentUser) -> None:
    if actor.role is Role.ADMIN:
        assert_admin(actor)
        return
    if actor.role is not Role.FOUNDER:
        raise ForbiddenError
    if actor.created_at is None or not has_founder_access(
        subscription_status=actor.subscription_status,
        created_at=actor.created_at,
    ):
        raise ForbiddenError(
            "Your free trial has ended. Unlock SACI FundMe to continue.",
            {"reason": "payment_required"},
        )


def _product_response(product: Product) -> ProductResponse:
    return ProductResponse.model_validate(product)


def _enrolment_response(
    enrolment: ProductEnrolment, *, product: Product | None = None
) -> EnrolmentResponse:
    return EnrolmentResponse(
        id=enrolment.id,
        product_id=enrolment.product_id,
        user_id=enrolment.user_id,
        created_at=enrolment.created_at,
        product=_product_response(product) if product is not None else None,
    )


# ---------------------------------------------------------------------------
# Unlock (D21)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Catalogue (T3.2 / D18)
# ---------------------------------------------------------------------------


async def create_product(
    session: AsyncSession, actor: CurrentUser, payload: ProductCreate
) -> ProductResponse:
    assert_admin(actor)
    products = ProductRepository(session)
    if await products.get_by_slug(payload.slug) is not None:
        raise ConflictError(
            "A product with this slug already exists.",
            {"reason": "slug_taken"},
        )
    if payload.kind is ProductKind.EVENT and payload.event_starts_at is None:
        raise InvalidRequestError(
            "Events require event_starts_at.",
            {"reason": "event_starts_at_required"},
        )

    product = await products.add(
        Product(
            kind=payload.kind,
            slug=payload.slug,
            title=payload.title,
            description=payload.description,
            regions=list(payload.regions),
            gap_tags=list(payload.gap_tags),
            stripe_price_id=payload.stripe_price_id,
            amount_minor=payload.amount_minor,
            currency=payload.currency,
            event_starts_at=payload.event_starts_at,
            event_location=payload.event_location,
            active=payload.active,
        )
    )
    await record_action(
        session,
        AuditAction.PRODUCT_CREATED,
        actor_id=actor.id,
        target_type="product",
        target_id=str(product.id),
        details={"slug": product.slug, "kind": product.kind.value},
    )
    return _product_response(product)


async def update_product(
    session: AsyncSession,
    actor: CurrentUser,
    product_id: uuid.UUID,
    payload: ProductUpdate,
) -> ProductResponse:
    assert_admin(actor)
    products = ProductRepository(session)
    product = await products.get(product_id)
    if product is None:
        raise NotFoundError

    data = payload.model_dump(exclude_unset=True)
    if (
        product.kind is ProductKind.EVENT
        and "event_starts_at" in data
        and data["event_starts_at"] is None
    ):
        raise InvalidRequestError(
            "Events require event_starts_at.",
            {"reason": "event_starts_at_required"},
        )

    for key, value in data.items():
        setattr(product, key, value)
    await session.flush()
    await record_action(
        session,
        AuditAction.PRODUCT_UPDATED,
        actor_id=actor.id,
        target_type="product",
        target_id=str(product.id),
        details={"fields": sorted(data.keys()), "active": product.active},
    )
    return _product_response(product)


async def list_products(
    session: AsyncSession,
    *,
    region: str | None = None,
    kind: ProductKind | None = None,
    limit: int = 50,
    offset: int = 0,
    include_inactive: bool = False,
) -> ProductPage:
    """Public catalogue browse — active products only unless admin asks otherwise."""
    if region is not None:
        code = region.strip().upper()
        if code != "*" and (len(code) != 2 or not code.isalpha()):
            raise InvalidRequestError(
                "region must be an ISO 3166-1 alpha-2 code.",
                {"reason": "invalid_region"},
            )
        region = code

    items, total = await ProductRepository(session).list_products(
        region=region,
        kind=kind,
        active_only=not include_inactive,
        limit=limit,
        offset=offset,
    )
    return ProductPage(
        items=[_product_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


async def get_product(
    session: AsyncSession, product_id: uuid.UUID, *, include_inactive: bool = False
) -> ProductResponse:
    product = await ProductRepository(session).get(product_id)
    if product is None or (not product.active and not include_inactive):
        raise NotFoundError
    return _product_response(product)


async def create_product_checkout(
    session: AsyncSession,
    actor: CurrentUser,
    product: Product,
    *,
    settings: Settings | None = None,
) -> CheckoutSessionResponse:
    """Checkout for a paid catalogue product (`kind=product` metadata)."""
    if not product.stripe_price_id:
        raise InvalidRequestError(
            "This product does not require payment.",
            {"reason": "product_free"},
        )

    settings = settings or get_settings()
    users = UserRepository(session)
    user = await users.get_by_id(actor.id)
    if user is None:
        raise NotFoundError

    _configure_stripe(settings)
    base = settings.app_link_base_url.rstrip("/")
    success = (
        settings.stripe_checkout_success_url.strip()
        or f"{base}/founder/programmes?checkout=success"
    )
    cancel = (
        settings.stripe_checkout_cancel_url.strip()
        or f"{base}/founder/programmes?checkout=cancel"
    )

    metadata = {
        "user_id": str(user.id),
        "kind": PRODUCT_METADATA_KIND,
        "product_id": str(product.id),
    }
    create_kwargs: dict[str, Any] = {
        "mode": "payment",
        "line_items": [{"price": product.stripe_price_id, "quantity": 1}],
        "success_url": success,
        "cancel_url": cancel,
        "client_reference_id": str(user.id),
        "metadata": metadata,
        "payment_intent_data": {"metadata": metadata},
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

    amount = int(checkout.amount_total or product.amount_minor or 0)
    currency = str(checkout.currency or product.currency or "usd").upper()
    await PurchaseRepository(session).add(
        Purchase(
            user_id=user.id,
            kind=PurchaseKind.PRODUCT,
            status=PurchaseStatus.PENDING,
            amount_minor=amount,
            currency=currency,
            stripe_checkout_session_id=session_id,
            product_id=product.id,
        )
    )

    customer_id = checkout.customer
    if customer_id and not user.stripe_customer_id:
        user.stripe_customer_id = str(customer_id)
        await session.flush()

    return CheckoutSessionResponse(checkout_url=url, session_id=session_id)


async def enrol_in_product(
    session: AsyncSession,
    actor: CurrentUser,
    product_id: uuid.UUID,
    *,
    settings: Settings | None = None,
) -> ProductEnrolResult:
    """Enrol a founder with access; free immediately, paid via Checkout."""
    _require_founder_access(actor)

    products = ProductRepository(session)
    product = await products.get(product_id)
    if product is None or not product.active:
        raise NotFoundError

    enrolments = ProductEnrolmentRepository(session)
    existing = await enrolments.get(actor.id, product.id)
    if existing is not None:
        raise ConflictError(
            "Already enrolled in this product.",
            {"reason": "already_enrolled"},
        )

    if product.stripe_price_id:
        checkout = await create_product_checkout(
            session, actor, product, settings=settings
        )
        return ProductEnrolResult(
            status="checkout_required",
            checkout=checkout,
        )

    enrolment = await enrolments.add(
        ProductEnrolment(user_id=actor.id, product_id=product.id)
    )
    await record_action(
        session,
        AuditAction.PRODUCT_ENROLLED,
        actor_id=actor.id,
        target_type="product_enrolment",
        target_id=str(enrolment.id),
        details={
            "product_id": str(product.id),
            "paid": False,
        },
    )
    return ProductEnrolResult(
        status="enrolled",
        enrolment=_enrolment_response(enrolment, product=product),
    )


async def list_my_enrolments(
    session: AsyncSession,
    actor: CurrentUser,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[EnrolmentResponse]:
    if actor.role not in {Role.FOUNDER, Role.ADMIN}:
        raise ForbiddenError
    if actor.role is Role.ADMIN:
        assert_admin(actor)

    enrolments, _total = await ProductEnrolmentRepository(session).list_for_user(
        actor.id, limit=limit, offset=offset
    )
    products = ProductRepository(session)
    responses: list[EnrolmentResponse] = []
    for enrolment in enrolments:
        product = await products.get(enrolment.product_id)
        responses.append(_enrolment_response(enrolment, product=product))
    return responses


# ---------------------------------------------------------------------------
# Stripe webhooks
# ---------------------------------------------------------------------------


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
        checkout = _stripe_mapping(event["data"]["object"])
        await _apply_checkout_completed(session, checkout)
    elif event_type.startswith("identity.verification_session."):
        from app.modules.investor import service as investor_service

        identity_obj = _stripe_mapping(event["data"]["object"])
        await investor_service.apply_identity_webhook_event(
            session, event_type, identity_obj
        )
    # Future: invoice.* / customer.subscription.* if Billing is adopted (D21).

    await events.record(event_id, event_type)
    return {"status": "ok"}


def _stripe_mapping(value: Any) -> dict[str, Any]:
    """Plain dict from a StripeObject or mapping (SDK versions differ)."""
    if isinstance(value, dict):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        converted = to_dict()
        if isinstance(converted, dict):
            return converted
    return {key: value[key] for key in value}


async def _apply_checkout_completed(
    session: AsyncSession, checkout: dict[str, Any]
) -> None:
    raw_metadata = checkout.get("metadata") or {}
    metadata = _stripe_mapping(raw_metadata) if raw_metadata else {}
    kind = metadata.get("kind")
    if kind == UNLOCK_METADATA_KIND:
        await _apply_unlock_checkout(session, checkout, metadata)
        return
    if kind == PRODUCT_METADATA_KIND:
        await _apply_product_checkout(session, checkout, metadata)
        return

    logger.info(
        "stripe checkout ignored",
        extra={"context": {"reason": "unknown_kind"}},
    )


def _parse_user_id(
    checkout: dict[str, Any], metadata: dict[str, Any]
) -> uuid.UUID | None:
    user_id_raw = metadata.get("user_id") or checkout.get("client_reference_id")
    if not user_id_raw:
        logger.warning("stripe checkout missing user_id")
        return None
    try:
        return uuid.UUID(str(user_id_raw))
    except ValueError:
        logger.warning("stripe checkout bad user_id")
        return None


async def _apply_unlock_checkout(
    session: AsyncSession,
    checkout: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    user_id = _parse_user_id(checkout, metadata)
    if user_id is None:
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


async def _apply_product_checkout(
    session: AsyncSession,
    checkout: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    user_id = _parse_user_id(checkout, metadata)
    if user_id is None:
        return

    product_id_raw = metadata.get("product_id")
    if not product_id_raw:
        logger.warning("stripe product checkout missing product_id")
        return
    try:
        product_id = uuid.UUID(str(product_id_raw))
    except ValueError:
        logger.warning("stripe product checkout bad product_id")
        return

    users = UserRepository(session)
    user = await users.get_by_id(user_id)
    if user is None:
        logger.warning("stripe checkout user missing")
        return

    product = await ProductRepository(session).get(product_id)
    if product is None:
        logger.warning("stripe product checkout product missing")
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
                kind=PurchaseKind.PRODUCT,
                status=PurchaseStatus.PENDING,
                amount_minor=amount,
                currency=currency,
                stripe_checkout_session_id=session_id,
                product_id=product.id,
            )
        )
    else:
        purchase.product_id = product.id
        purchase.kind = PurchaseKind.PRODUCT

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

    enrolments = ProductEnrolmentRepository(session)
    enrolment = await enrolments.get(user.id, product.id)
    if enrolment is None:
        enrolment = await enrolments.add(
            ProductEnrolment(user_id=user.id, product_id=product.id)
        )

    await session.flush()
    await record_action(
        session,
        AuditAction.PURCHASE_COMPLETED,
        actor_id=None,
        target_type="purchase",
        target_id=str(purchase.id),
        details={
            "kind": PurchaseKind.PRODUCT.value,
            "user_id": str(user.id),
            "product_id": str(product.id),
            "enrolment_id": str(enrolment.id),
        },
    )
    await record_action(
        session,
        AuditAction.PRODUCT_ENROLLED,
        actor_id=None,
        target_type="product_enrolment",
        target_id=str(enrolment.id),
        details={
            "product_id": str(product.id),
            "paid": True,
            "purchase_id": str(purchase.id),
        },
    )
