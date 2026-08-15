"""Stripe webhook signature verification and subscription entitlement (D24)."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import InvalidRequestError
from app.core.security import AccountStatus, Role, SubscriptionStatus
from app.modules.commerce import service
from app.modules.commerce.models import PurchaseKind, PurchaseStatus
from app.modules.commerce.repository import PurchaseRepository
from app.modules.identity.models import User
from app.modules.identity.repository import UserRepository
from tests.conftest import requires_database

pytestmark = [pytest.mark.security, pytest.mark.integration, requires_database]

WEBHOOK_SECRET = "whsec_test_secret_value_for_unit_tests"


@pytest.fixture(autouse=True)
def stripe_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("STRIPE_PRICE_ID_UNLOCK", "price_test_unlock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _sign(payload: bytes, secret: str = WEBHOOK_SECRET) -> str:
    timestamp = int(time.time())
    scheme = stripe.WebhookSignature._compute_signature(  # noqa: SLF001
        f"{timestamp}.{payload.decode('utf-8')}", secret
    )
    return f"t={timestamp},v1={scheme}"


async def _founder(session: AsyncSession) -> User:
    user = User(
        email=f"founder-{uuid.uuid4().hex[:10]}@company.test",
        password_hash="x" * 60,
        role=Role.FOUNDER,
        status=AccountStatus.ACTIVE,
        email_verified_at=datetime.now(UTC),
        subscription_status=SubscriptionStatus.NONE,
    )
    session.add(user)
    await session.flush()
    return user


async def _deliver(session: AsyncSession, event: dict) -> dict[str, str]:
    payload = json.dumps(event).encode()
    return await service.handle_stripe_webhook(
        session, payload=payload, signature=_sign(payload)
    )


def _checkout_event(user_id: uuid.UUID, session_id: str = "cs_test_1") -> dict:
    return {
        "id": f"evt_{uuid.uuid4().hex}",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "object": "checkout.session",
                "mode": "subscription",
                "amount_total": 7900,
                "currency": "usd",
                "customer": "cus_test_1",
                "subscription": "sub_test_1",
                "client_reference_id": str(user_id),
                "metadata": {"user_id": str(user_id), "kind": "unlock"},
            }
        },
    }


def _subscription_event(
    *,
    event_type: str,
    status: str,
    customer: str = "cus_test_1",
    subscription_id: str = "sub_test_1",
    user_id: uuid.UUID | None = None,
) -> dict:
    obj: dict = {
        "id": subscription_id,
        "object": "subscription",
        "status": status,
        "customer": customer,
        "metadata": {"kind": "unlock"},
    }
    if user_id is not None:
        obj["metadata"]["user_id"] = str(user_id)
    return {
        "id": f"evt_{uuid.uuid4().hex}",
        "object": "event",
        "type": event_type,
        "data": {"object": obj},
    }


def _invoice_event(*, failed: bool, customer: str = "cus_test_1") -> dict:
    return {
        "id": f"evt_{uuid.uuid4().hex}",
        "object": "event",
        "type": "invoice.payment_failed" if failed else "invoice.paid",
        "data": {
            "object": {
                "id": f"in_{uuid.uuid4().hex[:8]}",
                "object": "invoice",
                "customer": customer,
                "subscription": "sub_test_1",
                "paid": not failed,
            }
        },
    }


async def test_invalid_signature_is_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(InvalidRequestError) as exc:
        await service.handle_stripe_webhook(
            db_session, payload=b"{}", signature="t=1,v1=bad"
        )
    assert exc.value.details is not None
    assert exc.value.details["reason"] == "invalid_signature"


async def test_checkout_completed_grants_subscription(
    db_session: AsyncSession,
) -> None:
    user = await _founder(db_session)
    result = await _deliver(db_session, _checkout_event(user.id))
    assert result["status"] == "ok"

    await db_session.refresh(user)
    assert user.subscription_status is SubscriptionStatus.ACTIVE
    assert user.stripe_customer_id == "cus_test_1"
    assert user.stripe_subscription_id == "sub_test_1"

    purchase = await PurchaseRepository(db_session).latest_completed_unlock(user.id)
    assert purchase is not None
    assert purchase.kind is PurchaseKind.UNLOCK
    assert purchase.status is PurchaseStatus.COMPLETED
    assert purchase.amount_minor == 7900


async def test_duplicate_event_is_idempotent(db_session: AsyncSession) -> None:
    user = await _founder(db_session)
    event = _checkout_event(user.id, session_id="cs_test_dup")
    payload = json.dumps(event).encode()
    signature = _sign(payload)

    first = await service.handle_stripe_webhook(
        db_session, payload=payload, signature=signature
    )
    second = await service.handle_stripe_webhook(
        db_session, payload=payload, signature=signature
    )
    assert first["status"] == "ok"
    assert second["status"] == "duplicate"

    refreshed = await UserRepository(db_session).get_by_id(user.id)
    assert refreshed is not None
    assert refreshed.subscription_status is SubscriptionStatus.ACTIVE


async def test_subscription_updated_marks_past_due(db_session: AsyncSession) -> None:
    user = await _founder(db_session)
    await _deliver(db_session, _checkout_event(user.id))
    result = await _deliver(
        db_session,
        _subscription_event(
            event_type="customer.subscription.updated",
            status="past_due",
            user_id=user.id,
        ),
    )
    assert result["status"] == "ok"
    await db_session.refresh(user)
    assert user.subscription_status is SubscriptionStatus.PAST_DUE


async def test_subscription_deleted_cancels(db_session: AsyncSession) -> None:
    user = await _founder(db_session)
    await _deliver(db_session, _checkout_event(user.id))
    await _deliver(
        db_session,
        _subscription_event(
            event_type="customer.subscription.deleted",
            status="canceled",
            user_id=user.id,
        ),
    )
    await db_session.refresh(user)
    assert user.subscription_status is SubscriptionStatus.CANCELED


async def test_invoice_paid_restores_active(db_session: AsyncSession) -> None:
    user = await _founder(db_session)
    await _deliver(db_session, _checkout_event(user.id))
    await _deliver(db_session, _invoice_event(failed=True))
    await db_session.refresh(user)
    assert user.subscription_status is SubscriptionStatus.PAST_DUE
    await _deliver(db_session, _invoice_event(failed=False))
    await db_session.refresh(user)
    assert user.subscription_status is SubscriptionStatus.ACTIVE


async def test_grandfathered_unlock_ignores_cancel(
    db_session: AsyncSession,
) -> None:
    user = await _founder(db_session)
    user.subscription_status = SubscriptionStatus.ACTIVE
    user.stripe_customer_id = "cus_legacy"
    await db_session.flush()

    await _deliver(
        db_session,
        _subscription_event(
            event_type="customer.subscription.deleted",
            status="canceled",
            customer="cus_legacy",
        ),
    )
    await db_session.refresh(user)
    assert user.subscription_status is SubscriptionStatus.ACTIVE
    assert user.stripe_subscription_id is None
