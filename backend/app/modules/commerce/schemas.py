"""Commerce request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
