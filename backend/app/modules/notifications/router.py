"""Notifications HTTP endpoints (T5.3).

Layer: **router** (ARCHITECTURE.md section 3) -- HTTP only. Validate the request
with `schemas`, call exactly one `service` method, return a response schema.
No business logic, no database access, no LLM calls.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import CurrentUserDep, SessionDep
from app.core.errors import error_responses
from app.modules.notifications import inbox
from app.modules.notifications.schemas import (
    MarkReadRequest,
    NotificationPage,
)

router = APIRouter(tags=["notifications"])


@router.get(
    "/notifications",
    response_model=NotificationPage,
    summary="Your in-app inbox",
    description=(
        "Newest first. Only the caller's own rows. Empty until an event "
        "(audit ready, task assigned, evidence result, meeting booked) "
        "writes one."
    ),
    responses=error_responses(401, 403, 422),
)
async def list_notifications(
    actor: CurrentUserDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NotificationPage:
    return await inbox.list_for_user(session, actor, limit=limit, offset=offset)


@router.post(
    "/notifications/read",
    response_model=NotificationPage,
    summary="Mark notifications as read",
    description=(
        "Idempotent. Ids that are not yours, already read, or unknown are "
        "ignored — the response is the inbox after the write."
    ),
    responses=error_responses(401, 403, 422),
)
async def mark_notifications_read(
    payload: MarkReadRequest, actor: CurrentUserDep, session: SessionDep
) -> NotificationPage:
    await inbox.mark_read(session, actor, payload.ids)
    return await inbox.list_for_user(session, actor, limit=20, offset=0)
