"""Commerce business logic: Checkout + verified Stripe webhooks.

Layer: **service** (ARCHITECTURE.md section 3). Entitlement is granted only
from verified webhooks (CLAUDE.md section 4, DECISIONS.md D24) — never from a
client-reported payment state.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import stripe
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import (
    ConfigurationError,
    ConflictError,
    ForbiddenError,
    InvalidRequestError,
    NotFoundError,
)
from app.core.security import CurrentUser, Role, SubscriptionStatus, assert_admin
from app.modules.commerce.matching import gap_applies, region_applies
from app.modules.commerce.models import (
    Enrolment,
    Product,
    ProductKind,
    Purchase,
    PurchaseKind,
    PurchaseStatus,
)
from app.modules.commerce.repository import (
    EnrolmentRepository,
    ProductRepository,
    PurchaseRepository,
    StripeWebhookEventRepository,
)
from app.modules.commerce.schemas import (
    CheckoutSessionResponse,
    EnrolmentPage,
    EnrolmentResponse,
    EnrolResult,
    PortalSessionResponse,
    ProductCreate,
    ProductPage,
    ProductResponse,
    ProductUpdate,
    UnlockReceiptResponse,
)
from app.modules.identity.models import AuditAction, User
from app.modules.identity.repository import UserRepository
from app.modules.identity.service import record_action
from app.modules.intake import service as intake
from app.modules.readiness import service as readiness
from app.modules.readiness.generation import TaskStatus

logger = logging.getLogger(__name__)

UNLOCK_METADATA_KIND = "unlock"
CATALOGUE_METADATA_KIND = "catalogue"

_PRODUCT_DENIED = "No such product."


def _configure_stripe(settings: Settings) -> None:
    key = settings.stripe_secret_key
    if key is None or not key.get_secret_value().strip():
        raise ConfigurationError
    stripe.api_key = key.get_secret_value()


def _already_subscribed(user: User) -> bool:
    """Active, dunning, or a grandfathered D21 one-time unlock."""
    return user.subscription_status in {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAST_DUE,
    }


async def create_unlock_checkout(
    session: AsyncSession,
    actor: CurrentUser,
    *,
    settings: Settings | None = None,
) -> CheckoutSessionResponse:
    """Create a Stripe Checkout Session for the monthly founder subscription."""
    if actor.role is not Role.FOUNDER:
        raise ForbiddenError("Only founders can subscribe.")

    settings = settings or get_settings()
    price_id = settings.stripe_price_id_unlock.strip()
    if not price_id:
        raise ConfigurationError

    users = UserRepository(session)
    user = await users.get_by_id(actor.id)
    if user is None:
        raise NotFoundError

    if _already_subscribed(user):
        raise ConflictAlreadyUnlockedError()

    _configure_stripe(settings)
    success = (
        settings.stripe_checkout_success_url.strip()
        or f"{settings.app_link_base_url.rstrip('/')}/founder/billing?checkout=success"
    )
    cancel = (
        settings.stripe_checkout_cancel_url.strip()
        or f"{settings.app_link_base_url.rstrip('/')}/founder/billing?checkout=cancel"
    )

    create_kwargs: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success,
        "cancel_url": cancel,
        "client_reference_id": str(user.id),
        "metadata": {
            "user_id": str(user.id),
            "kind": UNLOCK_METADATA_KIND,
        },
        "subscription_data": {
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
    """Founder already holds an active or past-due subscription."""

    def __init__(self) -> None:
        super().__init__(
            "This account already has a subscription.",
            {"reason": "already_unlocked"},
        )


async def create_billing_portal(
    session: AsyncSession,
    actor: CurrentUser,
    *,
    settings: Settings | None = None,
) -> PortalSessionResponse:
    """Open the Stripe Customer Portal so the founder can update the card or cancel."""
    if actor.role is not Role.FOUNDER:
        raise ForbiddenError("Only founders can manage billing.")

    settings = settings or get_settings()
    users = UserRepository(session)
    user = await users.get_by_id(actor.id)
    if user is None:
        raise NotFoundError
    if not user.stripe_customer_id:
        raise InvalidRequestError(
            "No billing account yet. Subscribe first.",
            {"reason": "no_customer"},
        )

    _configure_stripe(settings)
    return_url = (
        settings.stripe_checkout_success_url.strip()
        or f"{settings.app_link_base_url.rstrip('/')}/founder/billing"
    )
    portal = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=return_url,
    )
    url = portal.url
    if not url:
        raise ConfigurationError
    return PortalSessionResponse(portal_url=url)


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


def _checkout_configured(product: Product) -> bool:
    if not product.amount_minor and not (product.stripe_price_id or "").strip():
        return True
    return bool((product.stripe_price_id or "").strip())


def _to_product(product: Product) -> ProductResponse:
    return ProductResponse(
        id=product.id,
        kind=product.kind,
        slug=product.slug,
        title=product.title,
        description=product.description,
        regions=list(product.regions),
        gap_tags=list(product.gap_tags),
        amount_minor=product.amount_minor,
        currency=product.currency,
        event_starts_at=product.event_starts_at,
        event_location=product.event_location,
        active=product.active,
        checkout_configured=_checkout_configured(product),
    )


async def create_product(
    session: AsyncSession, actor: CurrentUser, payload: ProductCreate
) -> ProductResponse:
    """SACI admin: add one catalogue item."""
    assert_admin(actor)
    products = ProductRepository(session)
    row = Product(
        kind=payload.kind,
        slug=payload.slug,
        title=payload.title,
        description=payload.description,
        regions=payload.regions,
        gap_tags=payload.gap_tags,
        amount_minor=payload.amount_minor,
        currency=payload.currency,
        stripe_price_id=payload.stripe_price_id,
        event_starts_at=payload.event_starts_at,
        event_location=payload.event_location,
        active=payload.active,
    )
    try:
        async with session.begin_nested():
            await products.add(row)
    except IntegrityError:
        raise ConflictError(
            "A product with this slug already exists.",
            {"reason": "duplicate_slug"},
        ) from None
    await record_action(
        session,
        AuditAction.PRODUCT_CREATED,
        actor_id=actor.id,
        target_type="product",
        target_id=str(row.id),
        details={"slug": row.slug, "kind": row.kind.value},
    )
    return _to_product(row)


async def update_product(
    session: AsyncSession,
    actor: CurrentUser,
    product_id: uuid.UUID,
    payload: ProductUpdate,
) -> ProductResponse:
    """SACI admin: revise or retire a catalogue item."""
    assert_admin(actor)
    products = ProductRepository(session)
    row = await products.get(product_id)
    if row is None:
        raise NotFoundError(_PRODUCT_DENIED)
    changes = payload.model_dump(exclude_unset=True)
    if "kind" in changes:
        kind = changes["kind"]
        if kind is ProductKind.EVENT:
            starts = changes.get("event_starts_at", row.event_starts_at)
            location = changes.get("event_location", row.event_location)
            if starts is None or not (location or "").strip():
                raise InvalidRequestError(
                    "events require event_starts_at and event_location",
                    {"reason": "event_fields_required"},
                )
    for field, value in changes.items():
        setattr(row, field, value)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        raise ConflictError(
            "A product with this slug already exists.",
            {"reason": "duplicate_slug"},
        ) from None
    await record_action(
        session,
        AuditAction.PRODUCT_UPDATED,
        actor_id=actor.id,
        target_type="product",
        target_id=str(row.id),
        details={"fields": sorted(changes)},
    )
    return _to_product(row)


async def list_products(
    session: AsyncSession,
    actor: CurrentUser,
    *,
    region: str | None = None,
    kind: ProductKind | None = None,
    limit: int = 20,
    offset: int = 0,
) -> ProductPage:
    """Browse the catalogue. Inactive items are admin-only."""
    items, total = await ProductRepository(session).list_page(
        region=region,
        kind=kind,
        include_inactive=actor.role is Role.ADMIN and actor.mfa_enabled,
        limit=limit,
        offset=offset,
    )
    return ProductPage(
        items=[_to_product(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


async def get_product(
    session: AsyncSession, actor: CurrentUser, product_id: uuid.UUID
) -> ProductResponse:
    """Read one catalogue item. Inactive items are hidden from non-admins."""
    row = await ProductRepository(session).get(product_id)
    if row is None or (
        not row.active and not (actor.role is Role.ADMIN and actor.mfa_enabled)
    ):
        raise NotFoundError(_PRODUCT_DENIED)
    return _to_product(row)


async def enrol_product(
    session: AsyncSession, actor: CurrentUser, product_id: uuid.UUID
) -> EnrolResult:
    """Take a catalogue item: free enrols immediately, paid opens Checkout."""
    if actor.role is not Role.FOUNDER:
        raise ForbiddenError("Only founders can enrol in a programme.")
    products = ProductRepository(session)
    row = await products.get(product_id)
    if row is None or not row.active:
        raise NotFoundError(_PRODUCT_DENIED)

    enrolments = EnrolmentRepository(session)
    existing = await enrolments.get_for_user_product(actor.id, row.id)
    if existing is not None:
        return EnrolResult(status="enrolled", checkout_url=None)

    paid = bool(row.amount_minor) or bool(row.stripe_price_id)
    if not paid:
        await enrolments.add(Enrolment(user_id=actor.id, product_id=row.id))
        return EnrolResult(status="enrolled", checkout_url=None)

    if not (row.stripe_price_id or "").strip():
        raise InvalidRequestError(
            "This programme is not available for purchase yet.",
            {"reason": "checkout_not_configured"},
        )
    url = await _create_catalogue_checkout(session, actor, row)
    return EnrolResult(status="checkout_required", checkout_url=url)


async def _create_catalogue_checkout(
    session: AsyncSession, actor: CurrentUser, product: Product
) -> str:
    settings = get_settings()
    _configure_stripe(settings)
    users = UserRepository(session)
    user = await users.get_by_id(actor.id)
    if user is None:
        raise NotFoundError

    base = settings.app_link_base_url.rstrip("/")
    success = (
        settings.stripe_checkout_success_url.strip()
        or f"{base}/founder/programmes?checkout=success"
    )
    cancel = (
        settings.stripe_checkout_cancel_url.strip()
        or f"{base}/founder/programmes?checkout=cancel"
    )
    create_kwargs: dict[str, Any] = {
        "mode": "payment",
        "line_items": [{"price": product.stripe_price_id, "quantity": 1}],
        "success_url": success,
        "cancel_url": cancel,
        "client_reference_id": str(user.id),
        "metadata": {
            "user_id": str(user.id),
            "kind": CATALOGUE_METADATA_KIND,
            "product_id": str(product.id),
        },
        "payment_intent_data": {
            "metadata": {
                "user_id": str(user.id),
                "kind": CATALOGUE_METADATA_KIND,
                "product_id": str(product.id),
            }
        },
    }
    if user.stripe_customer_id:
        create_kwargs["customer"] = user.stripe_customer_id
    else:
        create_kwargs["customer_email"] = user.email
        create_kwargs["customer_creation"] = "always"

    checkout = stripe.checkout.Session.create(**create_kwargs)
    url = checkout.url
    if not url:
        raise ConfigurationError
    await PurchaseRepository(session).add(
        Purchase(
            user_id=user.id,
            product_id=product.id,
            kind=PurchaseKind.CATALOGUE,
            status=PurchaseStatus.PENDING,
            amount_minor=int(checkout.amount_total or product.amount_minor or 0),
            currency=str(checkout.currency or product.currency or "usd").upper(),
            stripe_checkout_session_id=str(checkout.id),
        )
    )
    customer_id = checkout.customer
    if customer_id and not user.stripe_customer_id:
        user.stripe_customer_id = str(customer_id)
        await session.flush()
    return url


async def list_enrolments(
    session: AsyncSession,
    actor: CurrentUser,
    *,
    limit: int = 20,
    offset: int = 0,
) -> EnrolmentPage:
    """The caller's own enrolments."""
    rows, total = await EnrolmentRepository(session).list_for_user(
        actor.id, limit=limit, offset=offset
    )
    return EnrolmentPage(
        items=[
            EnrolmentResponse(
                id=enrolment.id,
                product_id=enrolment.product_id,
                created_at=enrolment.created_at,
                product=_to_product(product) if product is not None else None,
            )
            for enrolment, product in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


async def list_recommendations(
    session: AsyncSession,
    actor: CurrentUser,
    startup_id: uuid.UUID,
    *,
    limit: int = 20,
    offset: int = 0,
) -> ProductPage:
    """Active catalogue items that match this startup's open gaps and country."""
    profile = await intake.get_profile(session, actor, startup_id)
    tasks, _ = await readiness.list_tasks(
        session, actor, profile.id, status=TaskStatus.OPEN, limit=100, offset=0
    )
    gaps = [task.dimension.value for task in tasks]
    matched = [
        product
        for product in await ProductRepository(session).list_active()
        if region_applies(product.regions, profile.country)
        and gap_applies(product.gap_tags, gaps)
    ]
    page = matched[offset : offset + limit]
    return ProductPage(
        items=[_to_product(item) for item in page],
        total=len(matched),
        limit=limit,
        offset=offset,
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

    payload_object = _as_dict(event["data"]["object"])
    if event_type == "checkout.session.completed":
        await _apply_checkout_completed(session, payload_object)
    elif event_type == "customer.subscription.updated":
        await _apply_subscription_event(session, payload_object)
    elif event_type == "customer.subscription.deleted":
        await _apply_subscription_event(session, payload_object, force_canceled=True)
    elif event_type == "invoice.paid":
        await _apply_invoice_event(session, payload_object, failed=False)
    elif event_type == "invoice.payment_failed":
        await _apply_invoice_event(session, payload_object, failed=True)

    await events.record(event_id, event_type)
    return {"status": "ok"}


async def _apply_checkout_completed(
    session: AsyncSession, checkout: dict[str, Any]
) -> None:
    metadata = checkout.get("metadata") or {}
    kind = metadata.get("kind")
    if kind == CATALOGUE_METADATA_KIND:
        await _apply_catalogue_checkout(session, checkout)
        return
    if kind != UNLOCK_METADATA_KIND:
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
    if customer:
        user.stripe_customer_id = str(customer)
    subscription = checkout.get("subscription")
    if subscription:
        user.stripe_subscription_id = str(subscription)

    await _set_subscription_status(
        session, user, SubscriptionStatus.ACTIVE, source="checkout.session.completed"
    )

    await record_action(
        session,
        AuditAction.PURCHASE_COMPLETED,
        actor_id=None,
        target_type="purchase",
        target_id=str(purchase.id),
        details={"kind": PurchaseKind.UNLOCK.value, "user_id": str(user.id)},
    )


async def _apply_catalogue_checkout(
    session: AsyncSession, checkout: dict[str, Any]
) -> None:
    metadata = checkout.get("metadata") or {}
    user_id_raw = metadata.get("user_id") or checkout.get("client_reference_id")
    product_id_raw = metadata.get("product_id")
    if not user_id_raw or not product_id_raw:
        logger.warning("stripe catalogue checkout missing ids")
        return
    try:
        user_id = uuid.UUID(str(user_id_raw))
        product_id = uuid.UUID(str(product_id_raw))
    except ValueError:
        logger.warning("stripe catalogue checkout bad ids")
        return

    users = UserRepository(session)
    user = await users.get_by_id(user_id)
    product = await ProductRepository(session).get(product_id)
    if user is None or product is None:
        logger.warning("stripe catalogue checkout missing user or product")
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
                product_id=product.id,
                kind=PurchaseKind.CATALOGUE,
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

    enrolments = EnrolmentRepository(session)
    if await enrolments.get_for_user_product(user.id, product.id) is None:
        try:
            async with session.begin_nested():
                await enrolments.add(Enrolment(user_id=user.id, product_id=product.id))
        except IntegrityError:
            pass

    customer = checkout.get("customer")
    if customer and not user.stripe_customer_id:
        user.stripe_customer_id = str(customer)

    await record_action(
        session,
        AuditAction.PURCHASE_COMPLETED,
        actor_id=None,
        target_type="purchase",
        target_id=str(purchase.id),
        details={
            "kind": PurchaseKind.CATALOGUE.value,
            "user_id": str(user.id),
            "product_id": str(product.id),
        },
    )


def _as_dict(payload: Any) -> dict[str, Any]:
    """Stripe objects look like dicts but do not implement `.get`."""
    if isinstance(payload, dict):
        return payload
    to_dict = getattr(payload, "to_dict_recursive", None) or getattr(
        payload, "to_dict", None
    )
    if callable(to_dict):
        converted = to_dict()
        if isinstance(converted, dict):
            return converted
    return dict(payload)


def _is_grandfathered(user: User) -> bool:
    return (
        user.subscription_status is SubscriptionStatus.ACTIVE
        and not user.stripe_subscription_id
    )


def _status_from_stripe(stripe_status: str) -> SubscriptionStatus | None:
    if stripe_status in {"active", "trialing"}:
        return SubscriptionStatus.ACTIVE
    if stripe_status == "past_due":
        return SubscriptionStatus.PAST_DUE
    if stripe_status in {"canceled", "unpaid", "incomplete_expired"}:
        return SubscriptionStatus.CANCELED
    return None


async def _user_from_stripe(
    session: AsyncSession,
    payload: dict[str, Any],
    *,
    subscription_id: str | None = None,
) -> User | None:
    users = UserRepository(session)
    metadata = payload.get("metadata") or {}
    user_id_raw = metadata.get("user_id")
    if user_id_raw:
        try:
            found = await users.get_by_id(uuid.UUID(str(user_id_raw)))
            if found is not None:
                return found
        except ValueError:
            pass
    if subscription_id:
        found = await users.get_by_stripe_subscription_id(subscription_id)
        if found is not None:
            return found
    customer = payload.get("customer")
    if customer:
        return await users.get_by_stripe_customer_id(str(customer))
    return None


async def _set_subscription_status(
    session: AsyncSession,
    user: User,
    new_status: SubscriptionStatus,
    *,
    source: str,
) -> None:
    previous = user.subscription_status
    user.subscription_status = new_status
    await session.flush()
    if previous is new_status:
        return
    await record_action(
        session,
        AuditAction.SUBSCRIPTION_CHANGED,
        actor_id=None,
        target_type="user",
        target_id=str(user.id),
        details={
            "from": previous.value,
            "to": new_status.value,
            "source": source,
            "at": datetime.now(UTC).isoformat(),
        },
    )


async def _apply_subscription_event(
    session: AsyncSession,
    subscription: dict[str, Any],
    *,
    force_canceled: bool = False,
) -> None:
    subscription_id = str(subscription.get("id") or "")
    user = await _user_from_stripe(
        session, subscription, subscription_id=subscription_id or None
    )
    if user is None:
        logger.warning("stripe subscription event missing user")
        return
    if _is_grandfathered(user):
        return
    if subscription_id:
        user.stripe_subscription_id = subscription_id
    customer = subscription.get("customer")
    if customer and not user.stripe_customer_id:
        user.stripe_customer_id = str(customer)
    if force_canceled:
        await _set_subscription_status(
            session,
            user,
            SubscriptionStatus.CANCELED,
            source="customer.subscription.deleted",
        )
        return
    mapped = _status_from_stripe(str(subscription.get("status") or ""))
    if mapped is None:
        return
    await _set_subscription_status(
        session, user, mapped, source="customer.subscription.updated"
    )


async def _apply_invoice_event(
    session: AsyncSession, invoice: dict[str, Any], *, failed: bool
) -> None:
    subscription_id = invoice.get("subscription")
    user = await _user_from_stripe(
        session,
        invoice,
        subscription_id=str(subscription_id) if subscription_id else None,
    )
    if user is None:
        logger.warning("stripe invoice event missing user")
        return
    if _is_grandfathered(user):
        return
    if subscription_id and not user.stripe_subscription_id:
        user.stripe_subscription_id = str(subscription_id)
    customer = invoice.get("customer")
    if customer and not user.stripe_customer_id:
        user.stripe_customer_id = str(customer)
    new_status = (
        SubscriptionStatus.PAST_DUE if failed else SubscriptionStatus.ACTIVE
    )
    source = "invoice.payment_failed" if failed else "invoice.paid"
    await _set_subscription_status(session, user, new_status, source=source)
