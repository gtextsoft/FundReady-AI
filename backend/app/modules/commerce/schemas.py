"""Commerce request/response schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.commerce.matching import GLOBAL_REGION, normalise_region
from app.modules.commerce.models import ProductKind

_SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

_PRODUCT_EXAMPLE: dict[str, Any] = {
    "id": "7c2a1b0c-4d5e-6789-abcd-ef0123456789",
    "kind": "program",
    "slug": "unit-economics-clinic",
    "title": "Unit economics clinic",
    "description": "A four-week programme on pricing, CAC, and contribution margin.",
    "regions": ["*"],
    "gap_tags": ["unit_economics"],
    "amount_minor": None,
    "currency": None,
    "event_starts_at": None,
    "event_location": None,
    "active": True,
    "checkout_configured": True,
}


def _normalise_regions(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        item = normalise_region(raw)
        if item != GLOBAL_REGION and (len(item) != 2 or not item.isalpha()):
            raise ValueError("each region must be an ISO 3166-1 alpha-2 code or *")
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _normalise_tags(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        item = raw.strip().lower()
        if not item:
            continue
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


class ProductCreate(BaseModel):
    """Add one catalogue item."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "kind": "program",
                    "slug": "unit-economics-clinic",
                    "title": "Unit economics clinic",
                    "description": (
                        "A four-week programme on pricing, CAC, and "
                        "contribution margin."
                    ),
                    "regions": ["*"],
                    "gap_tags": ["unit_economics"],
                    "active": True,
                }
            ]
        },
    )

    kind: ProductKind
    slug: str = Field(min_length=2, max_length=80, pattern=_SLUG_PATTERN)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    regions: list[str] = Field(min_length=1)
    gap_tags: list[str] = Field(default_factory=list)
    amount_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    stripe_price_id: str | None = Field(default=None, max_length=255)
    event_starts_at: datetime | None = None
    event_location: str | None = Field(default=None, max_length=200)
    active: bool = True

    @field_validator("regions")
    @classmethod
    def _regions(cls, value: list[str]) -> list[str]:
        return _normalise_regions(value)

    @field_validator("gap_tags")
    @classmethod
    def _tags(cls, value: list[str]) -> list[str]:
        return _normalise_tags(value)

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @field_validator("stripe_price_id")
    @classmethod
    def _price_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _event_and_price_fields(self) -> "ProductCreate":
        if self.kind is ProductKind.EVENT and (
            self.event_starts_at is None or not (self.event_location or "").strip()
        ):
            raise ValueError("events require event_starts_at and event_location")
        if self.amount_minor is not None and self.currency is None:
            raise ValueError("currency is required when amount_minor is set")
        if self.amount_minor is None and self.currency is not None:
            raise ValueError("amount_minor is required when currency is set")
        return self


class ProductUpdate(BaseModel):
    """Revise a catalogue item. Omitted fields stay as they are."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"active": False}]},
    )

    kind: ProductKind | None = None
    slug: str | None = Field(
        default=None, min_length=2, max_length=80, pattern=_SLUG_PATTERN
    )
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    regions: list[str] | None = None
    gap_tags: list[str] | None = None
    amount_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    stripe_price_id: str | None = Field(default=None, max_length=255)
    event_starts_at: datetime | None = None
    event_location: str | None = Field(default=None, max_length=200)
    active: bool | None = None

    @field_validator("regions")
    @classmethod
    def _regions(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _normalise_regions(value)

    @field_validator("gap_tags")
    @classmethod
    def _tags(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _normalise_tags(value)

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @field_validator("stripe_price_id")
    @classmethod
    def _price_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ProductResponse(BaseModel):
    """One catalogue item as any signed-in caller sees it."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        json_schema_extra={"example": _PRODUCT_EXAMPLE},
    )

    id: UUID
    kind: ProductKind
    slug: str
    title: str
    description: str
    regions: list[str]
    gap_tags: list[str]
    amount_minor: int | None
    currency: str | None
    event_starts_at: datetime | None
    event_location: str | None
    active: bool
    checkout_configured: bool = Field(
        description=(
            "True when the item is free, or when a Stripe Price is attached. "
            "A priced item without `stripe_price_id` is listed but cannot enrol."
        )
    )


class ProductPage(BaseModel):
    """One page of catalogue items."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "items": [_PRODUCT_EXAMPLE],
                "total": 1,
                "limit": 20,
                "offset": 0,
            }
        },
    )

    items: list[ProductResponse]
    total: int
    limit: int
    offset: int


class EnrolmentResponse(BaseModel):
    """One founder's enrolment, with the catalogue item when it still exists."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "id": "8d3b2c1d-5e6f-7890-bcde-f01234567890",
                "product_id": "7c2a1b0c-4d5e-6789-abcd-ef0123456789",
                "created_at": "2026-08-15T10:00:00Z",
                "product": _PRODUCT_EXAMPLE,
            }
        },
    )

    id: UUID
    product_id: UUID
    created_at: datetime
    product: ProductResponse | None


class EnrolmentPage(BaseModel):
    """The caller's enrolments."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {"items": [], "total": 0, "limit": 20, "offset": 0}
        },
    )

    items: list[EnrolmentResponse]
    total: int
    limit: int
    offset: int


class EnrolResult(BaseModel):
    """Outcome of asking to take a catalogue item."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"status": "enrolled", "checkout_url": None},
                {
                    "status": "checkout_required",
                    "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_a1b2c3",
                },
            ]
        },
    )

    status: str = Field(description="`enrolled` or `checkout_required`.")
    checkout_url: str | None = None


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
