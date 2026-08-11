"""Commerce request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.commerce.models import ProductKind


class CheckoutSessionResponse(BaseModel):
    """Hosted Stripe Checkout URL for the founder unlock (DECISIONS.md D21)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_a1b2c3",
                    "session_id": "cs_test_a1b2c3",
                }
            ]
        }
    )

    checkout_url: str = Field(description="Open this URL to complete payment.")
    session_id: str = Field(description="Stripe Checkout Session id.")


class UnlockReceiptResponse(BaseModel):
    """Completed unlock purchase, when one exists."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "reference": "3f2a1b0c-4d5e-6789-abcd-ef0123456789",
                    "amount": 14900,
                    "currency": "USD",
                    "paid_at": "2026-08-10T12:00:00Z",
                }
            ]
        },
    )

    reference: str = Field(description="Our purchase id.")
    amount: int = Field(description="Amount in minor units (e.g. cents).")
    currency: str = Field(description="ISO 4217 currency code.")
    paid_at: datetime


def _normalise_country_codes(values: list[str]) -> list[str]:
    normalised: list[str] = []
    for raw in values:
        code = raw.strip().upper()
        if not code:
            continue
        if code != "*" and (len(code) != 2 or not code.isalpha()):
            raise ValueError("Each region must be an ISO 3166-1 alpha-2 code or `*`.")
        if code not in normalised:
            normalised.append(code)
    return normalised


class ProductCreate(BaseModel):
    """Admin: add one catalogue item (T3.2 / D18)."""

    model_config = ConfigDict(extra="forbid")

    kind: ProductKind
    slug: str = Field(
        min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    regions: list[str] = Field(
        default_factory=list,
        description="ISO alpha-2 country codes, or `*` for global.",
    )
    gap_tags: list[str] = Field(
        default_factory=list,
        description="Rubric / gap tags used for recommendation matching.",
    )
    stripe_price_id: str | None = Field(default=None, max_length=255)
    amount_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    event_starts_at: datetime | None = None
    event_location: str | None = Field(default=None, max_length=300)
    active: bool = True

    @field_validator("regions")
    @classmethod
    def validate_regions(cls, value: list[str]) -> list[str]:
        return _normalise_country_codes(value)

    @field_validator("gap_tags")
    @classmethod
    def validate_gap_tags(cls, value: list[str]) -> list[str]:
        return [tag.strip() for tag in value if tag.strip()]

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()


class ProductUpdate(BaseModel):
    """Admin: revise or retire (`active=false`) a catalogue item."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1)
    regions: list[str] | None = None
    gap_tags: list[str] | None = None
    stripe_price_id: str | None = Field(default=None, max_length=255)
    amount_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    event_starts_at: datetime | None = None
    event_location: str | None = Field(default=None, max_length=300)
    active: bool | None = None

    @field_validator("regions")
    @classmethod
    def validate_regions(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalise_country_codes(value)

    @field_validator("gap_tags")
    @classmethod
    def validate_gap_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [tag.strip() for tag in value if tag.strip()]

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()


class ProductResponse(BaseModel):
    """One catalogue product as returned to clients."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "id": "5f2b1c9e-0000-4000-8000-000000000010",
                "kind": "program",
                "slug": "funding-readiness-challenge",
                "title": "The Funding Readiness Challenge",
                "description": "Six-week programme for scores below the floor.",
                "regions": ["*"],
                "gap_tags": ["unit_economics", "market_opportunity"],
                "stripe_price_id": None,
                "amount_minor": None,
                "currency": None,
                "event_starts_at": None,
                "event_location": None,
                "active": True,
                "created_at": "2026-08-11T08:00:00Z",
            }
        },
    )

    id: uuid.UUID
    kind: ProductKind
    slug: str
    title: str
    description: str
    regions: list[str]
    gap_tags: list[str]
    stripe_price_id: str | None = None
    amount_minor: int | None = None
    currency: str | None = None
    event_starts_at: datetime | None = None
    event_location: str | None = None
    active: bool
    created_at: datetime


class ProductPage(BaseModel):
    """Paged catalogue listing (`items` / `total` / `limit` / `offset`)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {"items": [], "total": 0, "limit": 50, "offset": 0}
        },
    )

    items: list[ProductResponse]
    total: int = Field(description="Total matching products, ignoring pagination.")
    limit: int
    offset: int


class EnrolmentResponse(BaseModel):
    """One product enrolment for the caller."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "id": "5f2b1c9e-0000-4000-8000-000000000011",
                "product_id": "5f2b1c9e-0000-4000-8000-000000000010",
                "user_id": "5f2b1c9e-0000-4000-8000-000000000012",
                "created_at": "2026-08-11T09:00:00Z",
                "product": None,
            }
        },
    )

    id: uuid.UUID
    product_id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    product: ProductResponse | None = None


class ProductEnrolResult(BaseModel):
    """Immediate enrolment, or Checkout when the product is paid."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["enrolled", "checkout_required"]
    enrolment: EnrolmentResponse | None = None
    checkout: CheckoutSessionResponse | None = None
