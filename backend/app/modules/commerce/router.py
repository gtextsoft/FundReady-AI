"""Commerce HTTP endpoints.

Stripe Checkout for the founder unlock and the Stripe webhook receiver.

Layer: **router** (ARCHITECTURE.md section 3) -- HTTP only.
"""

from typing import Annotated

from fastapi import APIRouter, Header, Request, status

from app.core.deps import CurrentFounder, SessionDep
from app.core.errors import error_responses
from app.modules.commerce import service
from app.modules.commerce.schemas import CheckoutSessionResponse, UnlockReceiptResponse

router = APIRouter(tags=["commerce"])


@router.post(
    "/billing/checkout",
    response_model=CheckoutSessionResponse,
    summary="Start founder unlock Checkout",
    description=(
        "Creates a Stripe Checkout Session for the one-off founder unlock "
        "(DECISIONS.md D21). Open `checkout_url` in a browser or system web "
        "view. Entitlement is granted only after Stripe delivers a verified "
        "`checkout.session.completed` webhook — do not treat opening the URL "
        "as payment.\n\n"
        "`422` with `already_unlocked` when `subscription_status` is already "
        "`active`."
    ),
    responses=error_responses(401, 403, 422, 500),
)
async def start_checkout(
    actor: CurrentFounder, session: SessionDep
) -> CheckoutSessionResponse:
    return await service.create_unlock_checkout(session, actor)


@router.get(
    "/billing/unlock",
    response_model=UnlockReceiptResponse,
    summary="Completed unlock receipt",
    description="Returns the founder's completed unlock purchase, if any.",
    responses=error_responses(401, 403, 404),
)
async def read_unlock(
    actor: CurrentFounder, session: SessionDep
) -> UnlockReceiptResponse:
    return await service.get_unlock_receipt(session, actor)


@router.post(
    "/billing/webhooks/stripe",
    status_code=status.HTTP_200_OK,
    summary="Stripe webhook receiver",
    description=(
        "Verifies the Stripe signature header and applies entitlement changes. "
        "Idempotent on `event.id`. Not authenticated with a bearer token — "
        "Stripe signs the body instead."
    ),
    responses=error_responses(422, 500),
    include_in_schema=True,
)
async def stripe_webhook(
    request: Request,
    session: SessionDep,
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> dict[str, str]:
    if not stripe_signature:
        from app.core.errors import InvalidRequestError

        raise InvalidRequestError(
            "Missing Stripe-Signature header.",
            {"reason": "missing_signature"},
        )
    payload = await request.body()
    return await service.handle_stripe_webhook(
        session, payload=payload, signature=stripe_signature
    )
