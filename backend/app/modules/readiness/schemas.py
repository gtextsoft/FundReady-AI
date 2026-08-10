"""Readiness request/response schemas.

Layer: **schemas** (ARCHITECTURE.md section 3) -- Pydantic request and response
models, including the per-tier response serializers (summary vs full). Unknown
or extra fields are rejected. Tier filtering lives here and is enforced by the
service, never by the client (DECISIONS.md D8).

**There is no request schema for a task, and that is the design.** Nothing a
client sends creates, edits, or completes one: tasks are generated from an audit
(T3.1) and settled by evidence assessment (T3.5). `DECISIONS.md` D10 makes that
a product rule rather than an omission -- readiness is earned, so a writable
status would be a way to clear the investor-visibility gate without doing the
work. The absence of a `TaskUpdate` here is what enforces it.

**Tasks are founder-tier data.** They quote the rubric's findings about a
specific business, so nothing here is ever served to an investor: discovery
serves `investor.StartupCard` and only a SACI reveal goes further (D8). There is
consequently one serializer rather than three -- the tier boundary is that this
schema has no investor-facing route at all, not that it drops fields for one.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.audit.rubric.v1 import Dimension
from app.modules.readiness.evidence import AssessmentOutcome, EvidenceStatus
from app.modules.readiness.generation import Requirement, TaskStatus


class ReadinessTaskResponse(BaseModel):
    """One readiness task, as the founder sees it."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "id": "5f9b1c1e-6f5a-4c3b-9a1f-2d4e6a8c0b12",
                "startup_id": "0b6f0f2a-1c2d-4e5f-8a9b-0c1d2e3f4a5b",
                "audit_run_id": "b8eabf62-1f2e-4c3d-9a8b-7c6d5e4f3a2b",
                "dimension": "unit_economics",
                "action": (
                    "State customer acquisition cost and the period it was "
                    "measured over, with the spend it was derived from."
                ),
                "requirement": "required",
                "status": "open",
                "dimension_score": 41,
                "is_priority": True,
                "created_at": "2026-08-05T09:14:22Z",
                "updated_at": "2026-08-05T09:14:22Z",
            }
        },
    )

    id: uuid.UUID
    startup_id: uuid.UUID
    audit_run_id: uuid.UUID | None = Field(
        description=(
            "The audit run that most recently raised this gap, or `null` if "
            "that run has since been deleted. Use it to link the task back to "
            "the report that is asking for it."
        )
    )
    dimension: Dimension = Field(description="Which rubric dimension raised this gap.")
    action: str = Field(
        description="What to do, in the rubric's own wording, as issued."
    )
    requirement: Requirement = Field(
        description=(
            "`required` blocks investor visibility; `recommended` does not. "
            "Derived from the dimension's score against the readiness "
            "threshold, not from a model's opinion."
        )
    )
    status: TaskStatus = Field(
        description=(
            "Where the task sits in the evidence loop. Written by evidence "
            "assessment (T3.5), never by a client."
        )
    )
    dimension_score: int | None = Field(
        description=(
            "The 0-100 score that produced this task, or `null` when the "
            "dimension could not be assessed at all. Use it to order and to "
            "explain; do not render it to the founder as a grade."
        )
    )
    is_priority: bool = Field(
        description=(
            "Whether this is in the short list to show first. An audit marks at "
            "most five, one per weak dimension. If nothing is marked, show "
            "everything."
        )
    )
    assessment_attempts: int = Field(
        description="How many times evidence for this task has been graded."
    )
    attempts_remaining: int = Field(
        description=(
            "Graded attempts left before the task locks. At `0` a new upload is "
            "refused with `409` and only a SACI admin can reopen it."
        )
    )
    created_at: datetime
    updated_at: datetime


class ReadinessTaskPage(BaseModel):
    """One page of readiness tasks.

    Same shape as `investor.DiscoveryPage` -- `items`/`total`/`limit`/`offset` --
    because `CLAUDE.md` section 6 requires list conventions to be identical
    across endpoints and this is the first collection built after that gap was
    written down in TASKS.md. New collections adopt it at birth rather than
    being retrofitted; `GET /v1/startups/{id}/documents` is the one still owed
    the change, and it needs a version story because the mobile client already
    consumes its bare-array shape.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {"items": [], "total": 0, "limit": 50, "offset": 0}
        },
    )

    items: list[ReadinessTaskResponse]
    total: int = Field(description="Total matching tasks, ignoring pagination.")
    limit: int
    offset: int


class ReadinessSummary(BaseModel):
    """How much work stands between this startup and investor visibility.

    A separate, cheap read: a founder's home screen wants "3 of 11 done", and
    paging the whole task list to compute it would make every app launch a
    multi-page fetch.

    **Every count is scoped to the tasks the latest succeeded audit raised**, so
    `required_open == 0` means exactly what the discovery gate tests (T3.6) --
    not something adjacent to it. Counting every task ever generated would
    include gaps the current report no longer raises, and a progress bar that
    can never reach zero is worse than no progress bar.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "total": 44,
                "required_total": 31,
                "required_open": 29,
                "required_passed": 2,
                "recommended_total": 13,
                "has_audit": True,
                "gate_cleared": False,
                "discoverable": False,
            }
        },
    )

    total: int = Field(
        description="Tasks the latest succeeded audit raised, excluding retired ones."
    )
    required_total: int = Field(description="Tasks that block investor visibility.")
    required_open: int = Field(
        description=(
            "Required tasks not yet passed. **This is the number the gate "
            "tests.** Investor visibility needs it at zero, alongside a "
            "succeeded audit."
        )
    )
    required_passed: int = Field(
        description="Required tasks whose evidence has been assessed as sufficient."
    )
    recommended_total: int = Field(
        description="Tasks worth doing that do not block visibility."
    )
    has_audit: bool = Field(
        description=(
            "Whether a succeeded audit with a report exists. Without one there "
            "are no tasks and nothing to be discovered on."
        )
    )
    gate_cleared: bool = Field(
        description=(
            "`has_audit` **and** `required_open == 0`. This is eligibility, not "
            "visibility -- the founder must also have opted in."
        )
    )
    discoverable: bool = Field(
        description=(
            "Whether this startup actually appears in discovery right now: the "
            "gate cleared **and** the founder opted in via `publish`.\n\n"
            "**Not the same field as `StartupProfile.investor_visible`**, which "
            "is consent alone. This one is the answer to 'can an investor see "
            "me', which is what a founder is actually asking."
        )
    )


class EvidenceUploadRequest(BaseModel):
    """Declare a file before uploading it.

    Both fields are a **declaration**, not a fact: the server checks
    `content_type` against the allowlist and bakes it into the signature, then
    reads back what actually landed at `complete`. A client that declares a PDF
    and uploads a zip is refused by R2, not trusted.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "filename": "pricing-page-live.png",
                "content_type": "image/png",
            }
        },
    )

    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)


class EvidenceUploadTicket(BaseModel):
    """Where to send the file, and the limits it must respect."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "evidence_id": "9c2f4e10-7a1b-4d3c-8e5f-1a2b3c4d5e6f",
                "upload_url": "https://r2.example.com/evidence/...?X-Amz-Signature=...",
                "expires_in": 900,
                "max_bytes": 26214400,
            }
        },
    )

    evidence_id: uuid.UUID
    upload_url: str = Field(
        description=(
            "Single-use, single-key, expiring URL. `PUT` the raw bytes with the "
            "same `Content-Type` you declared. Never persist this."
        )
    )
    expires_in: int = Field(description="Seconds until `upload_url` stops working.")
    max_bytes: int = Field(description="Reject larger files client-side too.")


class EvidenceResponse(BaseModel):
    """One submission and, once graded, its verdict."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "id": "9c2f4e10-7a1b-4d3c-8e5f-1a2b3c4d5e6f",
                "task_id": "5f9b1c1e-6f5a-4c3b-9a1f-2d4e6a8c0b12",
                "filename": "pricing-page-live.png",
                "content_type": "image/png",
                "size_bytes": 184320,
                "status": "ready",
                "outcome": "needs_more",
                "reasons": [
                    "The screenshot shows a pricing page but carries no date "
                    "or URL, so it cannot be tied to your business. Re-submit "
                    "with the browser address bar visible."
                ],
                "assessed_at": "2026-08-05T11:04:19Z",
                "error_code": None,
                "created_at": "2026-08-05T11:02:02Z",
            }
        },
    )

    id: uuid.UUID
    task_id: uuid.UUID
    filename: str
    content_type: str | None
    size_bytes: int | None
    status: EvidenceStatus = Field(
        description=(
            "Upload lifecycle only. `pending` means the file has not arrived, "
            "`rejected` means it was refused and deleted. Grading is `outcome`."
        )
    )
    outcome: AssessmentOutcome | None = Field(
        description=(
            "`null` until graded. `pass`, `fail`, or `needs_more` — never "
            "inconclusive, because inconclusive *is* `needs_more`."
        )
    )
    reasons: list[str] | None = Field(
        description=(
            "Founder-facing, present on every outcome including a pass. Render "
            "them as a list; they are written to be read directly."
        )
    )
    assessed_at: datetime | None
    error_code: str | None = Field(
        description=(
            "Set when grading could not be completed at all (`assessment_failed`). "
            "Not a verdict — the task returns to `open` and no attempt is charged."
        )
    )
    created_at: datetime


class EvidencePage(BaseModel):
    """One page of submissions, newest first."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {"items": [], "total": 0, "limit": 50, "offset": 0}
        },
    )

    items: list[EvidenceResponse]
    total: int = Field(description="Total submissions for this task, ignoring paging.")
    limit: int
    offset: int


class EvidenceDownload(BaseModel):
    """A short-lived link to a stored submission."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "evidence_id": "9c2f4e10-7a1b-4d3c-8e5f-1a2b3c4d5e6f",
                "download_url": "https://r2.example.com/evidence/...?X-Amz-Signature=...",
                "expires_in": 900,
                "filename": "pricing-page-live.png",
            }
        },
    )

    evidence_id: uuid.UUID
    download_url: str
    expires_in: int
    filename: str
