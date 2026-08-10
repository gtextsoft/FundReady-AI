"""Founder trial and paid-unlock entitlement (DECISIONS.md D21).

Server-authoritative: the client must not invent trial end dates or treat a
local receipt as paid. Paid state comes only from Stripe webhooks writing
`subscription_status`; the trial window is derived from `users.created_at`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

from app.core.security import SubscriptionStatus

TRIAL_DAYS: Final = 14
"""Days of full founder access from account creation, before unlock is required."""


def trial_ends_at(created_at: datetime) -> datetime:
    """UTC instant when the free trial ends."""
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at + timedelta(days=TRIAL_DAYS)


def trial_active(created_at: datetime, *, now: datetime | None = None) -> bool:
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    return trial_ends_at(created_at) > instant


def is_paid(subscription_status: SubscriptionStatus) -> bool:
    """True when Stripe has granted the one-off unlock."""
    return subscription_status is SubscriptionStatus.ACTIVE


def has_founder_access(
    *,
    subscription_status: SubscriptionStatus,
    created_at: datetime,
    now: datetime | None = None,
) -> bool:
    """Paid unlock or still inside the server-computed trial window."""
    return is_paid(subscription_status) or trial_active(created_at, now=now)


__all__ = [
    "TRIAL_DAYS",
    "has_founder_access",
    "is_paid",
    "trial_active",
    "trial_ends_at",
]
