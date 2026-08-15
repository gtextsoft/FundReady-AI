"""Commerce HTTP endpoints.

Stripe Checkout for the founder unlock, the product catalogue (T3.2 / D18),
and the Stripe webhook receiver.

Layer: **router** (ARCHITECTURE.md section 3) -- HTTP only.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, status

from app.core.deps import (
    CurrentAdmin,
    CurrentFounder,
    CurrentUserDep,
    SessionDep,
)
from app.core.errors import error_responses
from app.modules.commerce import service
from app.modules.commerce.models import ProductKind
from app.modules.commerce.schemas import (
    CheckoutSessionResponse,
    EnrolmentPage,
    EnrolResult,
    PortalSessionResponse,
    ProductCreate,
    ProductPage,
    ProductResponse,
    ProductUpdate,
    UnlockReceiptResponse,
)

router = APIRouter(tags=["commerce"])

CATALOGUE_NOTE = (
    "\n\n**One catalogue, three kinds** (`program` · `mentorship` · `event`) "
    "per `DECISIONS.md` D18. Events carry `event_starts_at` and "
    "`event_location`. `regions` is ISO alpha-2 or `*` for everywhere. "
    "`gap_tags` match rubric dimensions (for example `unit_economics`) so a "
    "startup's open tasks can recommend the right item."
)


@router.post(
    "/billing/checkout",
    response_model=CheckoutSessionResponse,
    summary="Start founder subscription Checkout",
    description=(
        "Creates a Stripe Checkout Session for the monthly founder "
        "subscription (DECISIONS.md D24, `mode=subscription`). Open "
        "`checkout_url` in a browser. Entitlement is granted only after "
        "Stripe delivers a verified webhook — do not treat opening the URL "
        "as payment.\n\n"
        "`422` with `already_unlocked` when `subscription_status` is already "
        "`active` or `past_due`."
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
    "/billing/portal",
    response_model=PortalSessionResponse,
    summary="Open the Stripe billing portal",
    description=(
        "Creates a Stripe Customer Portal session so the founder can update "
        "the card or cancel the monthly subscription. Requires an existing "
        "Stripe customer (`422` with `no_customer` otherwise)."
    ),
    responses=error_responses(401, 403, 404, 422, 500),
)
async def start_billing_portal(
    actor: CurrentFounder, session: SessionDep
) -> PortalSessionResponse:
    return await service.create_billing_portal(session, actor)


@router.post(
    "/billing/webhooks/stripe",
    status_code=status.HTTP_200_OK,
    summary="Stripe webhook receiver",
    description=(
        "Verifies the Stripe signature header and applies entitlement changes. "
        "Handles `checkout.session.completed`, `customer.subscription.updated`, "
        "`customer.subscription.deleted`, `invoice.paid`, and "
        "`invoice.payment_failed`. Idempotent on `event.id`. Not authenticated "
        "with a bearer token — Stripe signs the body instead."
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


@router.get(
    "/products",
    response_model=ProductPage,
    summary="Browse the product catalogue",
    description=(
        "Programs, mentorship, and events SACI has listed, newest title first "
        "is not the order — title then id, so paging is stable.\n\n"
        "`region` keeps items whose `regions` include that ISO code or `*`. "
        "Founders and investors see **active** items only; an admin also sees "
        "retired ones." + CATALOGUE_NOTE
    ),
    responses=error_responses(401, 403, 422),
)
async def list_products(
    actor: CurrentUserDep,
    session: SessionDep,
    region: Annotated[str | None, Query(min_length=1, max_length=2)] = None,
    kind: Annotated[ProductKind | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProductPage:
    return await service.list_products(
        session, actor, region=region, kind=kind, limit=limit, offset=offset
    )


@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Read one catalogue item",
    description=(
        "A retired item is `404` for anyone who is not a SACI admin — the "
        "same answer as an unknown id." + CATALOGUE_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def read_product(
    product_id: uuid.UUID, actor: CurrentUserDep, session: SessionDep
) -> ProductResponse:
    return await service.get_product(session, actor, product_id)


@router.post(
    "/admin/products",
    status_code=status.HTTP_201_CREATED,
    response_model=ProductResponse,
    summary="Create a catalogue item",
    description=(
        "SACI admins only; MFA required. `409` when the slug is already "
        "taken. Events must include `event_starts_at` and `event_location`."
        + CATALOGUE_NOTE
    ),
    responses=error_responses(401, 403, 409, 422),
)
async def create_product(
    payload: ProductCreate, actor: CurrentAdmin, session: SessionDep
) -> ProductResponse:
    return await service.create_product(session, actor, payload)


@router.patch(
    "/admin/products/{product_id}",
    response_model=ProductResponse,
    summary="Update a catalogue item",
    description=(
        "SACI admins only; MFA required. Omitted fields stay as they are. "
        "Set `active` to `false` to retire an item without deleting it — "
        "enrolments and the `product_id` on a task survive." + CATALOGUE_NOTE
    ),
    responses=error_responses(401, 403, 404, 409, 422),
)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    actor: CurrentAdmin,
    session: SessionDep,
) -> ProductResponse:
    return await service.update_product(session, actor, product_id, payload)


@router.post(
    "/products/{product_id}/enrol",
    response_model=EnrolResult,
    summary="Enrol in a catalogue item",
    description=(
        "Founders only. A free item (`amount_minor` empty) enrols immediately "
        "and returns `{status: enrolled}`. A priced item with a Stripe Price "
        "returns `{status: checkout_required, checkout_url}` — entitlement "
        "arrives only after the verified webhook, the same rule as the unlock. "
        "Repeating the call after a successful enrolment is idempotent.\n\n"
        "`422` with `checkout_not_configured` when the item is priced but has "
        "no `stripe_price_id`."
    ),
    responses=error_responses(401, 403, 404, 422, 500),
)
async def enrol_product(
    product_id: uuid.UUID, actor: CurrentFounder, session: SessionDep
) -> EnrolResult:
    return await service.enrol_product(session, actor, product_id)


@router.get(
    "/me/enrolments",
    response_model=EnrolmentPage,
    summary="List the caller's enrolments",
    description="Newest first. The nested `product` is `null` if the item was deleted.",
    responses=error_responses(401, 403, 422),
)
async def list_enrolments(
    actor: CurrentUserDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EnrolmentPage:
    return await service.list_enrolments(session, actor, limit=limit, offset=offset)


@router.get(
    "/startups/{startup_id}/recommendations",
    response_model=ProductPage,
    summary="Catalogue items matched to this startup's gaps",
    description=(
        "Active items whose `gap_tags` overlap this startup's **open** "
        "readiness-task dimensions, and whose `regions` include the profile "
        "country or `*`.\n\n"
        "Ownership-checked: another founder's startup is `404`. An item with "
        "no `gap_tags` is browse-only and never appears here." + CATALOGUE_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def list_recommendations(
    startup_id: uuid.UUID,
    actor: CurrentUserDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProductPage:
    return await service.list_recommendations(
        session, actor, startup_id, limit=limit, offset=offset
    )
