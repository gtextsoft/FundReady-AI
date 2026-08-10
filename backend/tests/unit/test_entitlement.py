"""Server-authoritative trial and unlock entitlement (D21)."""

from datetime import UTC, datetime, timedelta

from app.core.entitlement import (
    TRIAL_DAYS,
    has_founder_access,
    is_paid,
    trial_active,
    trial_ends_at,
)
from app.core.security import SubscriptionStatus


def test_trial_ends_after_configured_days() -> None:
    created = datetime(2026, 1, 1, tzinfo=UTC)
    assert trial_ends_at(created) == created + timedelta(days=TRIAL_DAYS)


def test_trial_active_inside_window() -> None:
    created = datetime.now(UTC) - timedelta(days=1)
    assert trial_active(created) is True


def test_trial_inactive_after_window() -> None:
    created = datetime.now(UTC) - timedelta(days=TRIAL_DAYS + 1)
    assert trial_active(created) is False


def test_paid_is_active_only() -> None:
    assert is_paid(SubscriptionStatus.ACTIVE) is True
    assert is_paid(SubscriptionStatus.NONE) is False
    assert is_paid(SubscriptionStatus.PAST_DUE) is False
    assert is_paid(SubscriptionStatus.CANCELED) is False


def test_access_during_trial_without_payment() -> None:
    created = datetime.now(UTC)
    assert (
        has_founder_access(
            subscription_status=SubscriptionStatus.NONE, created_at=created
        )
        is True
    )


def test_access_after_trial_requires_payment() -> None:
    created = datetime.now(UTC) - timedelta(days=TRIAL_DAYS + 2)
    assert (
        has_founder_access(
            subscription_status=SubscriptionStatus.NONE, created_at=created
        )
        is False
    )
    assert (
        has_founder_access(
            subscription_status=SubscriptionStatus.ACTIVE, created_at=created
        )
        is True
    )
