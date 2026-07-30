"""Intake request/response schemas.

Layer: **schemas** (ARCHITECTURE.md section 3) -- Pydantic request and response
models, including the per-tier response serializers (summary vs full). Unknown
or extra fields are rejected. Tier filtering lives here and is enforced by the
service, never by the client (DECISIONS.md D8).
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.intake.documents import (
    MAX_UPLOAD_BYTES,
    DocumentKind,
    DocumentStatus,
    ScanStatus,
)
from app.modules.intake.fields import (
    FIELDS_BY_NAME,
    FieldSource,
    Stage,
)

__all__ = [
    "DocumentKind",
    "DocumentResponse",
    "DocumentStatus",
    "DownloadTicket",
    "FieldSource",
    "ProfileFieldValue",
    "ProfileResponse",
    "ScanStatus",
    "Stage",
    "StartupProfileCreate",
    "StartupProfileUpdate",
    "UploadRequest",
    "UploadTicket",
]

Country = Annotated[str, Field(min_length=2, max_length=2)]
Currency = Annotated[str, Field(min_length=3, max_length=3)]


class ProfileFieldValue(BaseModel):
    """One field, with where it came from and how sure we are.

    Provenance is part of the value rather than a parallel structure, so a field
    cannot be stored without it. The audit has to cite its evidence
    (CLAUDE.md section 5), and "the founder told us" is a materially different
    input from "read out of their filed accounts".
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "value": 4500000,
                    "source": "document",
                    "confidence": 0.82,
                    "document_id": "9b1c2d3e-4f5a-4b6c-8d7e-1f2a3b4c5d6e",
                },
                {"value": "Same-day parcels for Lagos merchants.", "source": "founder"},
            ]
        },
    )

    value: str | int | float | bool | None = Field(
        description="The value. Money is an integer in minor units."
    )
    source: FieldSource = Field(
        default=FieldSource.FOUNDER,
        description=(
            "`founder` when submitted directly, `document` when extracted from "
            "an upload, `inferred` when the model derived it."
        ),
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "0-1. Absent for `founder` values, which are taken as stated but "
            "are self-reported, not verified (DECISIONS.md D7)."
        ),
    )
    document_id: uuid.UUID | None = Field(
        default=None, description="Which upload this came from, when `document`."
    )


class _ProfileBody(BaseModel):
    """Shared shape for create and update."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    # Free text, not an enum: the platform must accept sectors that do not exist
    # yet (DECISIONS.md D11).
    sector: str | None = Field(
        default=None,
        max_length=120,
        description="Free text. Novel sectors are expected and supported.",
    )
    stage: Stage | None = None
    country: Country | None = Field(
        default=None, description="ISO 3166-1 alpha-2, e.g. `NG`, `GB`, `AE`."
    )
    currency: Currency | None = Field(
        default=None, description="ISO 4217, e.g. `NGN`, `GBP`, `USD`."
    )
    fields: dict[str, ProfileFieldValue] | None = Field(
        default=None,
        description=(
            "Any subset of the known profile fields. Unknown names are "
            "rejected rather than silently stored, so a typo does not become a "
            "field that no audit will ever read."
        ),
    )

    @field_validator("country")
    @classmethod
    def _upper_country(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @field_validator("fields")
    @classmethod
    def _known_fields_only(
        cls, value: dict[str, ProfileFieldValue] | None
    ) -> dict[str, ProfileFieldValue] | None:
        if value is None:
            return value
        unknown = sorted(set(value) - set(FIELDS_BY_NAME))
        if unknown:
            raise ValueError(f"unknown profile fields: {', '.join(unknown)}")
        return value


class StartupProfileCreate(_ProfileBody):
    """Create your startup profile.

    Every field is optional. A founder can start with a name and fill the rest
    in later, or let document extraction do it -- `missing_fields` on the
    response reports what an audit will still need.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "name": "Kanmi Logistics",
                    "sector": "last-mile delivery",
                    "stage": "seed",
                    "country": "NG",
                    "currency": "NGN",
                    "fields": {
                        "description": {
                            "value": "Same-day parcel delivery for Lagos merchants.",
                            "source": "founder",
                        },
                        "monthly_revenue_minor": {
                            "value": 4500000,
                            "source": "document",
                            "confidence": 0.82,
                        },
                    },
                }
            ]
        },
    )


class StartupProfileUpdate(_ProfileBody):
    """Update your startup profile.

    A partial update: omitted keys are left alone. Supplying `fields` merges
    per field name -- send a field to replace it, omit it to keep it.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "stage": "series_a",
                    "fields": {
                        "cash_on_hand_minor": {"value": 82000000, "source": "founder"}
                    },
                }
            ]
        },
    )


class ProfileResponse(BaseModel):
    """A startup profile as its owner (or a SACI admin) sees it.

    This is the **full** founder-facing view. The investor-facing summary tier
    is a separate serializer, built in T4.2 -- deliberately not a flag on this
    one, because a shared model with a hidden switch is how a full report leaks
    to the wrong tier (DECISIONS.md D8).
    """

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "3f2b1c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
                    "owner_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
                    "name": "Kanmi Logistics",
                    "sector": "last-mile delivery",
                    "stage": "seed",
                    "country": "NG",
                    "currency": "NGN",
                    "fields": {
                        "monthly_revenue_minor": {
                            "value": 4500000,
                            "source": "document",
                            "confidence": 0.82,
                            "document_id": None,
                        }
                    },
                    "missing_fields": [
                        "business_model",
                        "cash_on_hand_minor",
                        "monthly_costs_minor",
                        "team_size",
                    ],
                    "created_at": "2026-07-30T08:00:00Z",
                    "updated_at": "2026-07-30T08:30:00Z",
                }
            ]
        },
    )

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str | None
    sector: str | None
    stage: Stage | None
    country: str | None
    currency: str | None
    fields: dict[str, Any]
    missing_fields: list[str] = Field(
        description=(
            "Fields an audit still needs, computed on read rather than stored -- "
            "it is a function of the field set and the rubric version, so a "
            "persisted copy would go stale as soon as either changed."
        )
    )
    created_at: datetime
    updated_at: datetime


class ProfileConflict(BaseModel):
    """Returned when a founder already has a profile."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"detail": "You already have a profile."}]}
    )

    detail: Literal["You already have a profile."] = "You already have a profile."


# ---------------------------------------------------------------------------
# Documents (T1.5)
# ---------------------------------------------------------------------------

DOCUMENT_ID_EXAMPLE = "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"


class UploadRequest(BaseModel):
    """Ask for somewhere to put a file.

    Declaring the type up front is what lets the server bake it into the
    signature, so a mismatched upload is refused by storage rather than
    discovered afterwards.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "kind": "deck",
                    "filename": "kanmi-seed-deck.pdf",
                    "content_type": "application/pdf",
                }
            ]
        },
    )

    kind: DocumentKind = Field(
        description=(
            "What this file is. Steers extraction (T2.4); your declaration, "
            "not a verified fact."
        )
    )
    filename: str = Field(
        min_length=1,
        max_length=255,
        description=(
            "Display name only. It is **never** part of the storage path -- "
            "directory separators and control characters are stripped before "
            "it is stored."
        ),
    )
    content_type: str = Field(
        max_length=120,
        description=(
            "MIME type of the file you are about to send. Must be on the "
            "allowlist, and must match the `Content-Type` header you set on "
            "the upload or storage will reject it."
        ),
    )


class UploadTicket(BaseModel):
    """Where to send the bytes, and for how long.

    The URL is a **credential**: anyone holding it can write that one object
    until it expires. It is issued once, never stored, and not retrievable
    again -- ask for a new one if you lose it.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "document_id": DOCUMENT_ID_EXAMPLE,
                    "upload_url": "https://<account>.r2.cloudflarestorage.com/...",
                    "expires_in": 900,
                    "max_bytes": MAX_UPLOAD_BYTES,
                }
            ]
        }
    )

    document_id: uuid.UUID
    upload_url: str = Field(
        description=(
            "`PUT` the file here with the same `Content-Type` you declared. "
            "Send no authorization header -- the signature is the credential. "
            "Then call `POST /v1/documents/{document_id}/complete`."
        )
    )
    expires_in: int = Field(description="Seconds until the URL stops working.")
    max_bytes: int = Field(
        description=(
            "Reject anything larger before uploading. The server checks the "
            "real size afterwards and deletes what does not qualify."
        )
    )


class DownloadTicket(BaseModel):
    """A short-lived URL that reads one document."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "download_url": "https://<account>.r2.cloudflarestorage.com/...",
                    "expires_in": 900,
                }
            ]
        }
    )

    download_url: str = Field(
        description=(
            "`GET` this directly. It is a bearer credential for one file -- "
            "do not log it, share it, or put it somewhere it outlives its TTL."
        )
    )
    expires_in: int


class DocumentResponse(BaseModel):
    """A document's metadata. The bytes live in object storage."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": DOCUMENT_ID_EXAMPLE,
                    "startup_id": "3f2b1c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
                    "kind": "deck",
                    "filename": "kanmi-seed-deck.pdf",
                    "content_type": "application/pdf",
                    "size_bytes": 2418123,
                    "status": "ready",
                    "scan_status": "skipped",
                    "created_at": "2026-07-30T08:00:00Z",
                    "updated_at": "2026-07-30T08:01:12Z",
                }
            ]
        },
    )

    id: uuid.UUID
    startup_id: uuid.UUID
    kind: DocumentKind
    filename: str
    content_type: str | None = Field(
        description="What storage reported after upload. `null` until confirmed."
    )
    size_bytes: int | None = Field(
        description="Actual bytes stored. `null` until confirmed."
    )
    status: DocumentStatus = Field(
        description=(
            "`pending` until you call complete; `ready` once confirmed and "
            "accepted; `rejected` if it failed validation, in which case the "
            "file was deleted."
        )
    )
    scan_status: ScanStatus = Field(
        description=(
            "Malware scan result. **No scanner is wired yet**, so uploads "
            "settle at `skipped` rather than being reported `clean` "
            "(TASKS.md T5.5)."
        )
    )
    created_at: datetime
    updated_at: datetime

    # `owner_id` is deliberately absent: the caller is the owner (or a SACI
    # admin acting on their behalf), so it carries no information and is one
    # more internal id on the wire.
