"""Commerce HTTP endpoints.

Stripe Checkout for the founder unlock, the Stripe webhook receiver, and the
product / event catalogue (T3.2 / D18).

Layer: **router** (ARCHITECTURE.md section 3) -- HTTP only.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, status

from app.core.deps import (
    CurrentAdmin,
    CurrentFounder,
    CurrentUserDep,
    FounderWithAccess,
    SessionDep,
)
from app.core.errors import ForbiddenError, InvalidRequestError, error_responses
from app.core.security import Role
from app.modules.commerce import service
from app.modules.commerce.models import ProductKind
from app.modules.commerce.schemas import (
    CheckoutSessionResponse,
    EnrolmentResponse,
    ProductCreate,
    ProductEnrolResult,
    ProductPage,
    ProductResponse,
    ProductUpdate,
    UnlockReceiptResponse,
)

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
        "Stripe signs the body instead. Handles unlock (`kind=unlock`) and "
        "catalogue product (`kind=product`) Checkout completions."
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
        raise InvalidRequestError(
            "Missing Stripe-Signature header.",
            {"reason": "missing_signature"},
        )
    payload = await request.body()
    return await service.handle_stripe_webhook(
        session, payload=payload, signature=stripe_signature
    )


# ---------------------------------------------------------------------------
# Catalogue (T3.2)
# ---------------------------------------------------------------------------


@router.get(
    "/products",
    response_model=ProductPage,
    summary="Browse the product catalogue",
    description=(
        "Lists active programmes, mentorship offerings, and events. Filter by "
        "`region` (ISO alpha-2; products tagged `*` match every region) and "
        "`kind` (`program` · `mentorship` · `event`). Uses the standard paged "
        "envelope `{items, total, limit, offset}`."
    ),
    responses=error_responses(401, 422),
)
async def list_products(
    _actor: CurrentUserDep,
    session: SessionDep,
    region: Annotated[str | None, Query(max_length=2)] = None,
    kind: Annotated[ProductKind | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProductPage:
    return await service.list_products(
        session, region=region, kind=kind, limit=limit, offset=offset
    )


@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Read one catalogue product",
    description="Returns one active product. Retired products answer `404`.",
    responses=error_responses(401, 404),
)
async def read_product(
    product_id: UUID, _actor: CurrentUserDep, session: SessionDep
) -> ProductResponse:
    return await service.get_product(session, product_id)


@router.post(
    "/admin/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a catalogue product",
    description=(
        "Admin-only. Creates a programme, mentorship, or event. Set "
        "`active=false` later via PATCH to retire without deleting."
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
    summary="Update or retire a catalogue product",
    description=(
        "Admin-only. Partial update. Set `active=false` to retire — listings "
        "hide retired products; existing enrolments remain."
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    actor: CurrentAdmin,
    session: SessionDep,
) -> ProductResponse:
    return await service.update_product(session, actor, product_id, payload)


@router.post(
    "/products/{product_id}/enrol",
    response_model=ProductEnrolResult,
    summary="Enrol in a catalogue product",
    description=(
        "Founders with trial or paid access. Free products (`stripe_price_id` "
        "absent) enrol immediately (`status=enrolled`). Paid products create a "
        "Stripe Checkout Session (`status=checkout_required`); enrolment is "
        "granted only after a verified `checkout.session.completed` webhook "
        "with `metadata.kind=product`.\n\n"
        "`409` with `already_enrolled` when a seat already exists."
    ),
    responses=error_responses(401, 403, 404, 409, 422, 500),
)
async def enrol_in_product(
    product_id: UUID, actor: FounderWithAccess, session: SessionDep
) -> ProductEnrolResult:
    return await service.enrol_in_product(session, actor, product_id)


@router.get(
    "/me/enrolments",
    response_model=list[EnrolmentResponse],
    summary="List my product enrolments",
    description="The caller's catalogue enrolments, newest first.",
    responses=error_responses(401, 403),
)
async def list_my_enrolments(
    actor: CurrentUserDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[EnrolmentResponse]:
    if actor.role is Role.INVESTOR:
        raise ForbiddenError
    return await service.list_my_enrolments(session, actor, limit=limit, offset=offset)
