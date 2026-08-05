"""Readiness HTTP endpoints.

Readiness tasks, evidence assessment, re-audit, and the investor-visibility gate.

Layer: **router** (ARCHITECTURE.md section 3) -- HTTP only. Validate the request
with `schemas`, call exactly one `service` method, return a response schema.
No business logic, no database access, no LLM calls.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUserDep, SessionDep, SettingsDep
from app.core.errors import error_responses
from app.modules.readiness import service
from app.modules.readiness.evidence import MAX_UPLOAD_BYTES
from app.modules.readiness.generation import Requirement, TaskStatus
from app.modules.readiness.schemas import (
    EvidenceDownload,
    EvidencePage,
    EvidenceResponse,
    EvidenceUploadRequest,
    EvidenceUploadTicket,
    ReadinessSummary,
    ReadinessTaskPage,
    ReadinessTaskResponse,
)

router = APIRouter(tags=["readiness"])

TASK_NOTE = (
    "\n\n**Tasks are generated, never created.** They come from an audit's "
    "action plan, so there is no endpoint that creates, edits, or completes "
    "one -- a founder becomes investor-visible by doing the work and having "
    "evidence assessed (T3.5), not by marking a task done. A task belonging to "
    "another founder returns `404`, never `403`: a `403` would confirm the id "
    "is real."
)


@router.get(
    "/startups/{startup_id}/tasks",
    response_model=ReadinessTaskPage,
    summary="List readiness tasks",
    description=(
        "The tasks this startup's latest audit is asking for, ordered the way "
        "to show them: priority items first, then everything that blocks "
        "investor visibility, then the rest -- worst-scoring dimension first "
        "within each group.\n\n"
        "**`requirement` is the field that matters.** `required` blocks "
        "investor visibility; `recommended` does not. It is computed from the "
        "dimension's score against the readiness threshold, so it can change "
        "between audits as a founder improves.\n\n"
        "**Empty is a normal answer.** A startup with no succeeded audit has no "
        "tasks, and so does one whose audit found no unmet criteria. Neither is "
        "an error.\n\n"
        "`status` is `open` or `obsolete` today; the evidence states arrive "
        "with T3.5. `obsolete` means a later audit stopped raising the gap and "
        "nobody had worked on it -- filter it out unless you are showing "
        "history.\n\n"
        "`total` is the count ignoring pagination, so a client can render "
        '"page N of M".' + TASK_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def list_readiness_tasks(
    startup_id: uuid.UUID,
    actor: CurrentUserDep,
    session: SessionDep,
    status: Annotated[
        TaskStatus | None,
        Query(description="Only tasks in this state."),
    ] = None,
    requirement: Annotated[
        Requirement | None,
        Query(description="Only blocking (`required`) or only optional tasks."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReadinessTaskPage:
    items, total = await service.list_tasks(
        session,
        actor,
        startup_id,
        status=status,
        requirement=requirement,
        limit=limit,
        offset=offset,
    )
    return ReadinessTaskPage(
        items=[ReadinessTaskResponse.model_validate(task) for task in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/startups/{startup_id}/tasks/summary",
    response_model=ReadinessSummary,
    summary="Readiness progress at a glance",
    description=(
        "How much work stands between this startup and investor visibility, "
        "without paging the whole task list -- built for a home screen that "
        "loads on every app launch.\n\n"
        "`required_open` is the number the visibility gate will test (T3.6): "
        "when it reaches zero **and** the audit itself clears, the startup "
        "becomes discoverable. Until T3.5 lands, nothing can move a task off "
        "`open`, so expect `required_open` to equal `required_total`.\n\n"
        "Retired (`obsolete`) tasks are excluded from every count -- they are "
        "not work the founder owes." + TASK_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def read_readiness_summary(
    startup_id: uuid.UUID, actor: CurrentUserDep, session: SessionDep
) -> ReadinessSummary:
    return await service.summarise_tasks(session, actor, startup_id)


@router.get(
    "/startups/{startup_id}/tasks/{task_id}",
    response_model=ReadinessTaskResponse,
    summary="Read one readiness task",
    description=(
        "One task in full. `audit_run_id` links back to the report that is "
        "asking for it, so a client can show the founder why." + TASK_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def read_readiness_task(
    startup_id: uuid.UUID,
    task_id: uuid.UUID,
    actor: CurrentUserDep,
    session: SessionDep,
) -> ReadinessTaskResponse:
    task = await service.get_task(session, actor, startup_id, task_id)
    return ReadinessTaskResponse.model_validate(task)


EVIDENCE_FLOW = (
    "\n\n**Three steps, same as document upload.** 1) `POST` here to reserve a "
    "row and get a signed URL. 2) `PUT` the raw bytes to that URL with the "
    "same `Content-Type` you declared — this call does not go through this "
    "API. 3) `POST .../complete` so the server reads the object back and "
    "queues it for grading. A row that never reaches step 3 stays `pending` "
    "and is never graded."
)


@router.post(
    "/tasks/{task_id}/evidence",
    status_code=status.HTTP_201_CREATED,
    response_model=EvidenceUploadTicket,
    summary="Start an evidence upload",
    description=(
        "Reserves a submission against one readiness task and returns a URL to "
        "send the file to." + EVIDENCE_FLOW + "\n\n"
        "**Attach several files to one task when they belong together.** The "
        "grader reads a task's outstanding submissions as one set, so a "
        "screenshot plus the invoice that dates it are graded together and "
        "count as **one** attempt. Uploading them as separate attempts is "
        "strictly worse for the founder.\n\n"
        "`409` when the task has already passed (nothing left to prove) or when "
        "`attempts_remaining` is `0` — check that field before offering an "
        "upload button. `422` if `content_type` is not on the allowlist.\n\n"
        "Another founder's task returns `404`, never `403`."
    ),
    responses=error_responses(401, 403, 404, 409, 422),
)
async def start_evidence_upload(
    task_id: uuid.UUID,
    payload: EvidenceUploadRequest,
    actor: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> EvidenceUploadTicket:
    evidence, url = await service.request_evidence_upload(
        session,
        actor,
        task_id,
        filename=payload.filename,
        content_type=payload.content_type,
    )
    return EvidenceUploadTicket(
        evidence_id=evidence.id,
        upload_url=url,
        expires_in=settings.storage_signed_url_ttl_seconds,
        max_bytes=MAX_UPLOAD_BYTES,
    )


@router.post(
    "/evidence/{evidence_id}/complete",
    response_model=EvidenceResponse,
    summary="Confirm an evidence upload",
    description=(
        "Call this after the `PUT` succeeds. The server reads the object back "
        "and judges it on what actually arrived, not on what you declared.\n\n"
        "On success the task moves to `submitted` and grading is queued. "
        "**Grading is asynchronous** — poll the task or this submission until "
        "`outcome` is non-null. Expect seconds to a minute.\n\n"
        "A file that is missing, empty, larger than `max_bytes`, or of an "
        "unaccepted type is **deleted from storage** and marked `rejected`; "
        "`422` carries the reason in `details.reason` (`object_missing`, "
        "`empty_file`, `file_too_large`, `unsupported_content_type`). A "
        "rejected upload costs no assessment attempt.\n\n"
        "Safe to retry: calling it again on a confirmed submission returns it "
        "unchanged and does not queue a second grading."
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def complete_evidence_upload(
    evidence_id: uuid.UUID, actor: CurrentUserDep, session: SessionDep
) -> EvidenceResponse:
    evidence = await service.complete_evidence_upload(session, actor, evidence_id)
    return EvidenceResponse.model_validate(evidence)


@router.get(
    "/tasks/{task_id}/evidence",
    response_model=EvidencePage,
    summary="List evidence for a task",
    description=(
        "Every submission against this task, newest first, including `pending` "
        "and `rejected` ones so a founder can see an upload that never "
        "finished.\n\n"
        "`outcome` is `null` until graded. `reasons` is what to show the "
        "founder — it is written for them and is present on a pass as well as "
        "a failure."
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def list_evidence(
    task_id: uuid.UUID,
    actor: CurrentUserDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EvidencePage:
    items, total = await service.list_evidence(
        session, actor, task_id, limit=limit, offset=offset
    )
    return EvidencePage(
        items=[EvidenceResponse.model_validate(row) for row in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/evidence/{evidence_id}/download",
    response_model=EvidenceDownload,
    summary="Download a submission",
    description=(
        "A short-lived signed URL for a file the caller owns, or any file for a "
        "SACI admin reviewing a disputed grading.\n\n"
        "`404` for a `rejected` submission — its bytes were deleted at "
        "validation — and for one still `pending`."
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def download_evidence(
    evidence_id: uuid.UUID,
    actor: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> EvidenceDownload:
    evidence, url = await service.evidence_download_url(session, actor, evidence_id)
    return EvidenceDownload(
        evidence_id=evidence.id,
        download_url=url,
        expires_in=settings.storage_signed_url_ttl_seconds,
        filename=evidence.filename,
    )


@router.post(
    "/admin/tasks/{task_id}/reopen",
    response_model=ReadinessTaskResponse,
    summary="Reopen a locked task",
    description=(
        "**SACI admins only.** Resets a task's assessment attempts to zero and "
        "returns it to `open`, so the founder can submit again.\n\n"
        "This is the only way past the attempt cap, and therefore the only "
        "lever that undoes the guard on the investor-visibility gate — every "
        "call is written to the immutable audit log with the admin who made "
        "it.\n\n"
        "A `passed` task can be reopened too. That is the dispute path for a "
        "grading somebody believes was wrong, in either direction."
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def reopen_task(
    task_id: uuid.UUID, actor: CurrentUserDep, session: SessionDep
) -> ReadinessTaskResponse:
    task = await service.reopen_task(session, actor, task_id)
    return ReadinessTaskResponse.model_validate(task)
