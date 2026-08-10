"""Brokerage request/response schemas (T4.5, T4.6).

Layer: **schemas** (ARCHITECTURE.md section 3) -- Pydantic request and response
models, including the per-tier response serializers (summary vs full). Unknown
or extra fields are rejected. Tier filtering lives here and is enforced by the
service, never by the client (DECISIONS.md D8).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.brokerage.models import Interest, InterestStatus

__all__ = ["InterestCreate", "InterestResponse", "RevealResponse"]


class InterestCreate(BaseModel):
    """An investor asking SACI for an introduction."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "note": "Fits our Lagos fintech thesis. Cheque size 150-300k USD."
            }
        },
    )

    note: str | None = Field(
        default=None,
        max_length=1000,
        description=(
            "Context for SACI. **The founder never sees this** — an investor "
            "writes differently when the subject is not reading."
        ),
    )


class InterestResponse(BaseModel):
    """One expression of interest.

    **Carries no report content and no founder identity.** An investor holding
    an approved interest still sees only the summary card until a SACI admin
    reveals a report; approval means a conversation may proceed, not that the
    data is open.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "id": "6b1f0e2a-0000-4000-8000-000000000001",
                "startup_id": "5f2b1c9e-0000-4000-8000-000000000001",
                "status": "pending",
                "note": "Fits our Lagos fintech thesis.",
                "created_at": "2026-08-04T09:00:00Z",
                "decided_at": None,
                "revealed_run_ids": [],
            }
        },
    )

    id: uuid.UUID
    startup_id: uuid.UUID
    status: InterestStatus = Field(
        description=(
            "`pending` → SACI has not decided. `approved` → SACI will broker "
            "it; **still not a reveal**. `declined` and `withdrawn` are "
            "terminal."
        )
    )
    note: str | None = None
    created_at: datetime
    decided_at: datetime | None = None
    revealed_run_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description=(
            "Audit runs whose **full report** SACI has opened to this "
            "investor. Empty until a reveal happens. Read one with "
            "`GET /v1/interests/{id}/reports/{run_id}`."
        ),
    )

    @classmethod
    def of(
        cls, interest: Interest, revealed_run_ids: list[uuid.UUID] | None = None
    ) -> "InterestResponse":
        return cls(
            id=interest.id,
            startup_id=interest.startup_id,
            status=interest.status,
            note=interest.note,
            created_at=interest.created_at,
            decided_at=interest.decided_at,
            revealed_run_ids=revealed_run_ids or [],
        )


class RevealResponse(BaseModel):
    """Confirmation that one full report was opened to one investor."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "interest_id": "6b1f0e2a-0000-4000-8000-000000000001",
                "audit_run_id": "b8eabf62-0000-4000-8000-000000000002",
                "revealed_at": "2026-08-04T10:30:00Z",
            }
        },
    )

    interest_id: uuid.UUID
    audit_run_id: uuid.UUID
    revealed_at: datetime
