"""Brokerage HTTP endpoints (T4.5, T4.6).

Interest expressions, SACI approval, meetings, and full-report reveal.

Layer: **router** (ARCHITECTURE.md section 3) -- HTTP only. Validate the request
with `schemas`, call exactly one `service` method, return a response schema.
No business logic, no database access, no LLM calls.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentAdmin, CurrentUserDep, SessionDep
from app.core.errors import error_responses
from app.modules.audit.reports import AdminReport
from app.modules.brokerage import service
from app.modules.brokerage.models import InterestStatus
from app.modules.brokerage.schemas import (
    InterestCreate,
    InterestResponse,
    RevealResponse,
)

router = APIRouter(tags=["brokerage"])

BROKERAGE_NOTE = (
    "\n\n**SACI is the broker.** An investor never reaches a founder's full "
    "report by their own entitlement: they express interest, a SACI admin "
    "decides, and a separate admin action opens one report. Approval is not "
    "disclosure — an approved interest still sees only the summary card."
)


@router.post(
    "/discover/{startup_id}/interest",
    status_code=status.HTTP_201_CREATED,
    response_model=InterestResponse,
    summary="Express interest in a startup",
    description=(
        "Asks SACI for an introduction. **The founder is not notified and "
        "cannot see this** — they hear about it when SACI arranges the "
        "meeting.\n\n"
        "Idempotent: expressing interest twice returns the original record "
        "rather than creating a second. One per investor per startup.\n\n"
        "`404` if the startup has not published itself, identical to a startup "
        "that does not exist — you cannot express interest in something you "
        "were never shown." + BROKERAGE_NOTE
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def express_interest(
    startup_id: uuid.UUID,
    payload: InterestCreate,
    actor: CurrentUserDep,
    session: SessionDep,
) -> InterestResponse:
    return await service.express_interest(session, actor, startup_id, note=payload.note)


@router.get(
    "/interests",
    response_model=list[InterestResponse],
    summary="List interests",
    description=(
        "An investor sees their own, newest first. A **SACI admin sees every "
        "interest**, oldest first — it is a work queue, so the one waiting "
        "longest comes first.\n\n"
        "`revealed_run_ids` names the audit runs whose full report has been "
        "opened to that investor. Empty until a reveal happens." + BROKERAGE_NOTE
    ),
    responses=error_responses(401, 403, 422),
)
async def list_interests(
    actor: CurrentUserDep,
    session: SessionDep,
    interest_status: Annotated[InterestStatus | None, Query(alias="status")] = None,
) -> list[InterestResponse]:
    return await service.list_interests(session, actor, status=interest_status)


@router.post(
    "/admin/interests/{interest_id}/approve",
    response_model=InterestResponse,
    summary="Approve an interest",
    description=(
        "**SACI admins only.** Agrees to broker this introduction.\n\n"
        "**This is not a reveal.** The investor still sees only the summary "
        "card; opening the full report is a separate, deliberate action taken "
        "at the meeting.\n\n"
        "`409` if the interest has already been decided — the audit log "
        "records the decision that was taken, and a reversal would leave two "
        "contradictory rows. Reversing is a support conversation." + BROKERAGE_NOTE
    ),
    responses=error_responses(401, 403, 404, 409, 422),
)
async def approve_interest(
    interest_id: uuid.UUID, actor: CurrentAdmin, session: SessionDep
) -> InterestResponse:
    return await service.decide_interest(session, actor, interest_id, approve=True)


@router.post(
    "/admin/interests/{interest_id}/decline",
    response_model=InterestResponse,
    summary="Decline an interest",
    description=(
        "**SACI admins only.** Terminal, and audit-logged like an approval — "
        "who was turned away matters as much as who was not." + BROKERAGE_NOTE
    ),
    responses=error_responses(401, 403, 404, 409, 422),
)
async def decline_interest(
    interest_id: uuid.UUID, actor: CurrentAdmin, session: SessionDep
) -> InterestResponse:
    return await service.decide_interest(session, actor, interest_id, approve=False)


@router.post(
    "/admin/interests/{interest_id}/reveal",
    response_model=RevealResponse,
    summary="Reveal the full report to an investor",
    description=(
        "**SACI admins only, and the most consequential call in the API.** "
        "Opens the startup's latest completed audit — in full — to this one "
        "investor. Every call writes an immutable audit-log entry naming who "
        "opened what, for whom.\n\n"
        "Requires an **approved** interest; `409` otherwise, because revealing "
        "against a pending or declined one would make approval decorative.\n\n"
        "**Scoped to an audit run, not a startup.** A founder who re-audits "
        "produces a different report, and this investor's access is to what "
        "they were actually shown. Revealing again is idempotent — the same "
        "disclosure is returned, not a second one.\n\n"
        "`404` if the startup has no completed audit to reveal."
    ),
    responses=error_responses(401, 403, 404, 409, 422),
)
async def reveal_report(
    interest_id: uuid.UUID, actor: CurrentAdmin, session: SessionDep
) -> RevealResponse:
    return await service.reveal_report(session, actor, interest_id)


@router.get(
    "/interests/{interest_id}/reports/{run_id}",
    response_model=AdminReport,
    summary="Read a report revealed to you",
    description=(
        "The full report SACI opened to you at the meeting: both verdicts with "
        "their reasoning, the data-integrity score, every finding, and the "
        "action plan.\n\n"
        "**This is the only path by which an investor reads full report "
        "content.** Access is checked against an actual reveal, not against "
        "the interest's status — an approved interest with no reveal returns "
        "`404`.\n\n"
        "The same rendering rules as the founder report apply: "
        "`insufficient_data` is an absence and must never read as 'not "
        "fundable', and `provisional` must be labelled as provisional."
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def read_revealed_report(
    interest_id: uuid.UUID,
    run_id: uuid.UUID,
    actor: CurrentUserDep,
    session: SessionDep,
) -> AdminReport:
    return await service.read_revealed_report(session, actor, interest_id, run_id)
