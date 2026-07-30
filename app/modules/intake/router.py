"""Intake HTTP endpoints.

Structured founder intake and document ingestion into the Startup Profile.

Layer: **router** (ARCHITECTURE.md section 3) -- HTTP only. Validate the request
with `schemas`, call exactly one `service` method, return a response schema.
No business logic, no database access, no LLM calls.
"""

import uuid

from fastapi import APIRouter, status

from app.core.deps import CurrentUserDep, SessionDep
from app.core.errors import error_responses
from app.modules.intake import service
from app.modules.intake.models import StartupProfile
from app.modules.intake.schemas import (
    ProfileResponse,
    StartupProfileCreate,
    StartupProfileUpdate,
)

router = APIRouter(tags=["intake"])

OWNERSHIP_NOTE = (
    "\n\nYou can only reach your own profile. Another founder's id returns "
    "`404`, not `403` -- deliberately, so the API does not confirm which ids "
    "exist. SACI admins can read any profile."
)


def _serialise(profile: StartupProfile) -> ProfileResponse:
    """Attach the computed completeness to the stored record."""
    return ProfileResponse(
        id=profile.id,
        owner_id=profile.owner_id,
        name=profile.name,
        sector=profile.sector,
        stage=profile.stage,
        country=profile.country,
        currency=profile.currency,
        fields=profile.fields or {},
        missing_fields=service.missing_fields(profile),
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.post(
    "/startups",
    status_code=status.HTTP_201_CREATED,
    response_model=ProfileResponse,
    summary="Create your startup profile",
    description=(
        "Creates the profile for the authenticated founder. **Every field is "
        "optional** -- start with what you know and fill the rest in later, or "
        "let document extraction do it. `missing_fields` on the response says "
        "what an audit will still need.\n\n"
        "The owner is taken from your token, never from the request body.\n\n"
        "`409` if you already have a profile: one per founder in v1."
    ),
    responses=error_responses(401, 403, 409, 422),
)
async def create_profile(
    payload: StartupProfileCreate, actor: CurrentUserDep, session: SessionDep
) -> ProfileResponse:
    profile = await service.create_profile(
        session, actor, payload.model_dump(exclude_unset=True, mode="json")
    )
    return _serialise(profile)


@router.get(
    "/startups/me",
    response_model=ProfileResponse,
    summary="Your own startup profile",
    description=(
        "Returns the authenticated founder's profile without needing its id.\n\n"
        "`404` if you have not created one yet."
    ),
    responses=error_responses(401, 403, 404),
)
async def read_own_profile(
    actor: CurrentUserDep, session: SessionDep
) -> ProfileResponse:
    return _serialise(await service.get_own_profile(session, actor))


@router.get(
    "/startups/{profile_id}",
    response_model=ProfileResponse,
    summary="Read a startup profile",
    description="Returns one profile in full." + OWNERSHIP_NOTE,
    responses=error_responses(401, 403, 404, 422),
)
async def read_profile(
    profile_id: uuid.UUID, actor: CurrentUserDep, session: SessionDep
) -> ProfileResponse:
    return _serialise(await service.get_profile(session, actor, profile_id))


@router.patch(
    "/startups/{profile_id}",
    response_model=ProfileResponse,
    summary="Update a startup profile",
    description=(
        "A partial update: omitted keys are left as they were. `fields` merges "
        "by field name, so you can correct one value without resending the "
        "whole document -- and so document extraction does not overwrite what "
        "the founder typed.\n\n"
        "Unknown field names are rejected with `422` rather than stored, so a "
        "typo cannot become a field no audit will ever read." + OWNERSHIP_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def update_profile(
    profile_id: uuid.UUID,
    payload: StartupProfileUpdate,
    actor: CurrentUserDep,
    session: SessionDep,
) -> ProfileResponse:
    profile = await service.update_profile(
        session, actor, profile_id, payload.model_dump(exclude_unset=True, mode="json")
    )
    return _serialise(profile)
