"""Founder trial and paid-subscription entitlement (DECISIONS.md D24).

Server-authoritative: the client must not invent trial end dates or treat a
local receipt as paid. Paid state comes only from Stripe webhooks writing
`subscription_status`; the trial window is derived from `users.created_at`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

from app.core.security import SubscriptionStatus

TRIAL_DAYS: Final = 14
"""Days of full founder access from account creation, before subscribe."""


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
    """True while Stripe is collecting — including dunning (`past_due`)."""
    return subscription_status in {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAST_DUE,
    }


def has_founder_access(
    *,
    subscription_status: SubscriptionStatus,
    created_at: datetime,
    now: datetime | None = None,
) -> bool:
    """Paid subscription (or dunning) or still inside the server-computed trial."""
    return is_paid(subscription_status) or trial_active(created_at, now=now)


__all__ = [
    "TRIAL_DAYS",
    "has_founder_access",
    "is_paid",
    "trial_active",
    "trial_ends_at",
]
