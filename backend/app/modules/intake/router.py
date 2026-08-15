"""Intake HTTP endpoints.

Structured founder intake and document ingestion into the Startup Profile.

Layer: **router** (ARCHITECTURE.md section 3) -- HTTP only. Validate the request
with `schemas`, call exactly one `service` method, return a response schema.
No business logic, no database access, no LLM calls.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import (
    CurrentAdmin,
    CurrentUserDep,
    FounderWithAccess,
    SessionDep,
    SettingsDep,
    require_role,
)
from app.core.errors import error_responses
from app.core.security import CurrentUser, Role
from app.modules.intake import service
from app.modules.intake.documents import MAX_UPLOAD_BYTES
from app.modules.intake.fields import Stage
from app.modules.intake.models import CompanyVerificationStatus, StartupProfile
from app.modules.intake.registries import REGISTRIES
from app.modules.intake.schemas import (
    AdminStats,
    CorpusPage,
    DocumentResponse,
    DownloadTicket,
    ProfilePage,
    ProfileResponse,
    RegistriesResponse,
    RegistryEntry,
    StartupProfileCreate,
    StartupProfileUpdate,
    UploadRequest,
    UploadTicket,
    VerificationDecision,
)

router = APIRouter(tags=["intake"])

# Composed rather than `CurrentFounder`, because the permission matrix
# (AUTH.md section 5) grants "create/edit own startup" to founders *and*
# admins. `core.deps` asks for exactly this composition rather than widening
# the single-role aliases. An investor is refused: they reach startups through
# the summary tier in T4.2, never by owning one.
FounderOrAdmin = Annotated[CurrentUser, Depends(require_role(Role.FOUNDER, Role.ADMIN))]

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
        investor_visible=profile.investor_visible,
        published_at=profile.published_at,
        company_verification_status=profile.company_verification_status,
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
        "**If you omit `name`, it is filled in from your company email "
        "domain** -- `founder@acme.com` gives `Acme`. It is a starting point, "
        "not a verified company name: send `name` yourself to set it exactly, "
        "or correct it later with `PATCH /startups/{id}`. A name you do send "
        "is never overwritten.\n\n"
        "Founders (and SACI admins) only. `403` for an investor.\n\n"
        "`409` if you already have a profile: one per founder in v1."
    ),
    responses=error_responses(401, 403, 409, 422),
)
async def create_profile(
    payload: StartupProfileCreate, actor: FounderOrAdmin, session: SessionDep
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


PUBLISH_NOTE = (
    "\n\n**Publishing is consent, not eligibility.** Opting in says the founder "
    "is willing to be seen. Whether there is anything to *show* is decided "
    "separately: a startup appears in `GET /v1/discover` only once it also has "
    "a **succeeded audit**, because a card with no verdict tells an investor "
    "nothing and invites them to approach the founder directly — which is what "
    "the brokerage exists to prevent.\n\n"
    "So publishing before the first audit finishes is allowed and is not an "
    "error. The client should say so: *\"You'll appear to investors once your "
    'audit completes."* Poll the audit, not this endpoint.\n\n'
    "**What an investor then sees is the summary tier only** — the two verdict "
    "levels and scores, plus sector, stage and country. Never the submitted "
    "figures, the findings, the action plan, or any contact detail. The full "
    "report is revealed by a SACI admin at the meeting and by no other path."
)


@router.post(
    "/startups/{profile_id}/publish",
    response_model=ProfileResponse,
    summary="Publish to investors",
    description=(
        "Opt this startup in to investor discovery.\n\n"
        "Idempotent: publishing an already-published profile refreshes "
        "`published_at` and changes nothing else." + PUBLISH_NOTE + OWNERSHIP_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def publish_profile(
    profile_id: uuid.UUID, actor: FounderWithAccess, session: SessionDep
) -> ProfileResponse:
    profile = await service.set_discoverability(
        session, actor, profile_id, visible=True
    )
    return _serialise(profile)


@router.post(
    "/startups/{profile_id}/unpublish",
    response_model=ProfileResponse,
    summary="Withdraw from investor discovery",
    description=(
        "Opt out again. Takes effect immediately: the startup stops appearing "
        "in discovery and its card returns `404`.\n\n"
        "**Unconditional, unlike publishing.** Withdrawing consent is never "
        "harder than giving it, so there is no audit check and no waiting "
        "period.\n\n"
        "This does **not** retract a report a SACI admin has already revealed "
        "to an investor — that disclosure happened, and pretending otherwise "
        "would be worse than recording it. The reveal is kept in the audit log."
        + OWNERSHIP_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def unpublish_profile(
    profile_id: uuid.UUID, actor: CurrentUserDep, session: SessionDep
) -> ProfileResponse:
    profile = await service.set_discoverability(
        session, actor, profile_id, visible=False
    )
    return _serialise(profile)


@router.post(
    "/startups/{profile_id}/company-verification/submit",
    response_model=ProfileResponse,
    summary="Submit company registration for review",
    description=(
        "Moves `company_verification_status` to `in_review`. This is an "
        "admin badge, not a call to a company register (D7). Resubmitting a "
        "rejected profile is allowed; an already-accepted one is `409`."
        + OWNERSHIP_NOTE
    ),
    responses=error_responses(401, 403, 404, 409, 422),
)
async def submit_company_verification(
    profile_id: uuid.UUID, actor: CurrentUserDep, session: SessionDep
) -> ProfileResponse:
    profile = await service.submit_company_verification(session, actor, profile_id)
    return _serialise(profile)


@router.post(
    "/admin/startups/{profile_id}/company-verification",
    response_model=ProfileResponse,
    summary="Accept or reject company verification",
    description=(
        "**SACI admins with MFA only.** Sets `accepted` or `rejected` and "
        "notifies the founder."
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def decide_company_verification(
    profile_id: uuid.UUID,
    payload: VerificationDecision,
    actor: CurrentAdmin,
    session: SessionDep,
) -> ProfileResponse:
    profile = await service.decide_company_verification(
        session, actor, profile_id, accept=payload.accept
    )
    return _serialise(profile)


@router.get(
    "/admin/startups",
    response_model=ProfilePage,
    summary="List every startup profile",
    description=(
        "**SACI admins with MFA only.** Newest first. Filter with "
        "`company_verification_status`, `q` (name/sector/country), `country`, "
        "`sector`, `stage`, and `published`."
    ),
    responses=error_responses(401, 403, 422),
)
async def list_admin_startups(
    actor: CurrentAdmin,
    session: SessionDep,
    verification: Annotated[
        CompanyVerificationStatus | None, Query(alias="company_verification_status")
    ] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    country: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    sector: Annotated[str | None, Query(max_length=120)] = None,
    stage: Annotated[Stage | None, Query()] = None,
    published: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProfilePage:
    rows, total = await service.list_admin_startups(
        session,
        actor,
        verification=verification,
        q=q,
        country=country,
        sector=sector,
        stage=stage,
        published=published,
        limit=limit,
        offset=offset,
    )
    return ProfilePage(
        items=[_serialise(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/admin/stats",
    response_model=AdminStats,
    summary="Platform counters for the admin home",
    description=(
        "**SACI admins with MFA only.** Totals for startups, published "
        "profiles, succeeded audits, users by role, and pending interests."
    ),
    responses=error_responses(401, 403),
)
async def get_admin_stats(actor: CurrentAdmin, session: SessionDep) -> AdminStats:
    return await service.admin_stats(session, actor)


@router.get(
    "/admin/corpus",
    response_model=CorpusPage,
    summary="Export identity-stripped training records",
    description=(
        "**SACI admins with MFA only.** Paginated corpus for later model "
        "training. Legal names, registration numbers, founder contacts, and "
        "emails are stripped. Each export is audit-logged. Same filters as "
        "`GET /admin/startups` plus optional `startup_id`."
    ),
    responses=error_responses(401, 403, 422),
)
async def export_admin_corpus(
    actor: CurrentAdmin,
    session: SessionDep,
    verification: Annotated[
        CompanyVerificationStatus | None, Query(alias="company_verification_status")
    ] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    country: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    sector: Annotated[str | None, Query(max_length=120)] = None,
    stage: Annotated[Stage | None, Query()] = None,
    published: Annotated[bool | None, Query()] = None,
    startup_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CorpusPage:
    return await service.export_training_corpus(
        session,
        actor,
        verification=verification,
        q=q,
        country=country,
        sector=sector,
        stage=stage,
        published=published,
        startup_id=startup_id,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# Company registries (T1.6)
# ---------------------------------------------------------------------------


@router.get(
    "/registries",
    response_model=RegistriesResponse,
    summary="List company registries by country",
    description=(
        "Static reference data for the registration form: given an ISO "
        "3166-1 alpha-2 country code, which body registers companies there, "
        "what the certificate is called, and how to label the registration "
        "number field.\n\n"
        "**Key on ISO codes, not display names.** `NG` maps to CAC; "
        '`"Nigeria"` is not a key. Countries not in this list are still '
        "accepted — the founder fills legal name and number as free text "
        "and uploads a `registration_certificate`.\n\n"
        "Nothing here verifies a company exists (`DECISIONS.md` D7)."
    ),
    responses=error_responses(401, 403),
)
async def list_registries(_actor: CurrentUserDep) -> RegistriesResponse:
    return RegistriesResponse(
        registries=[
            RegistryEntry(
                country=entry.country,
                country_name=entry.country_name,
                registrar=entry.registrar,
                short_name=entry.short_name,
                document_name=entry.document_name,
                number_label=entry.number_label,
                number_example=entry.number_example,
            )
            for entry in REGISTRIES.values()
        ]
    )


# ---------------------------------------------------------------------------
# Documents (T1.5)
# ---------------------------------------------------------------------------

UPLOAD_FLOW = (
    "\n\n**The upload is three calls, and the bytes never pass through this "
    "API.** They go straight to object storage, which is why a 25 MB deck "
    "does not time out:\n\n"
    "1. `POST /v1/startups/{startup_id}/documents` -> a signed `upload_url`\n"
    "2. `PUT` the file to that URL with the `Content-Type` you declared, and "
    "**no** `Authorization` header -- the signature in the URL is the "
    "credential\n"
    "3. `POST /v1/documents/{document_id}/complete` -> the server reads the "
    "object back, checks it, and marks it `ready`\n\n"
    "A document that never reaches step 3 stays `pending` and is not "
    "downloadable. Signed URLs expire after `expires_in` seconds "
    "(15 minutes by default)."
)


@router.post(
    "/startups/{startup_id}/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=UploadTicket,
    summary="Start a document upload",
    description=(
        "Reserves a document and returns a URL to send the file to."
        + UPLOAD_FLOW
        + "\n\n`422` if the `content_type` is not on the allowlist -- check "
        "before uploading rather than after." + OWNERSHIP_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def start_upload(
    startup_id: uuid.UUID,
    payload: UploadRequest,
    actor: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> UploadTicket:
    document, url = await service.request_upload(
        session,
        actor,
        startup_id,
        kind=payload.kind,
        filename=payload.filename,
        content_type=payload.content_type,
    )
    return UploadTicket(
        document_id=document.id,
        upload_url=url,
        expires_in=settings.storage_signed_url_ttl_seconds,
        max_bytes=MAX_UPLOAD_BYTES,
    )


@router.post(
    "/documents/{document_id}/complete",
    response_model=DocumentResponse,
    summary="Confirm a document upload",
    description=(
        "Call this after the `PUT` succeeds. The server reads the object back "
        "from storage and judges it on what actually arrived -- not on what "
        "you declared.\n\n"
        "A file that is missing, empty, larger than `max_bytes`, or of an "
        "unaccepted type is **deleted from storage** and the document is "
        "marked `rejected`; `422` carries the reason in `details.reason` "
        "(`object_missing`, `empty_file`, `file_too_large`, "
        "`unsupported_content_type`).\n\n"
        "Safe to retry: calling it again on a `ready` document returns it "
        "unchanged." + OWNERSHIP_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def complete_upload(
    document_id: uuid.UUID, actor: CurrentUserDep, session: SessionDep
) -> DocumentResponse:
    document = await service.complete_upload(session, actor, document_id)
    return DocumentResponse.model_validate(document)


@router.get(
    "/startups/{startup_id}/documents",
    response_model=list[DocumentResponse],
    summary="List a startup's documents",
    description=(
        "Newest first. Includes `pending` and `rejected` documents, so the "
        "client can show an upload that stalled or was refused." + OWNERSHIP_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def list_documents(
    startup_id: uuid.UUID, actor: CurrentUserDep, session: SessionDep
) -> list[DocumentResponse]:
    documents = await service.list_documents(session, actor, startup_id)
    return [DocumentResponse.model_validate(document) for document in documents]


@router.get(
    "/documents/{document_id}/download",
    response_model=DownloadTicket,
    summary="Get a download URL for a document",
    description=(
        "Returns a short-lived URL, not the file. `GET` it directly with no "
        "`Authorization` header.\n\n"
        "**Treat the URL as a credential.** Anyone holding it can read the "
        "file until it expires -- do not log it or persist it.\n\n"
        "`422` if the document is not `ready`, or if a scan has flagged it."
        + OWNERSHIP_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def download_document(
    document_id: uuid.UUID,
    actor: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> DownloadTicket:
    url = await service.request_download(session, actor, document_id)
    return DownloadTicket(
        download_url=url, expires_in=settings.storage_signed_url_ttl_seconds
    )
