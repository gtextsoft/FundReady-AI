"""Notifications HTTP endpoints (T5.3).

In-app inbox for product events. Transactional email is sent by the service
helpers; these routes only read and mark the durable inbox rows.

Layer: **router** (ARCHITECTURE.md section 3) -- HTTP only. Validate the request
with `schemas`, call exactly one `service` method, return a response schema.
No business logic, no database access, no LLM calls.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUserDep, SessionDep
from app.core.errors import error_responses
from app.modules.notifications import service
from app.modules.notifications.schemas import MarkReadRequest, NotificationPage

router = APIRouter(tags=["notifications"])


@router.get(
    "/notifications",
    response_model=NotificationPage,
    summary="List notifications",
    description=(
        "The caller's in-app inbox, newest first. `total` ignores pagination "
        "so a client can render unread badges and page counts.\n\n"
        "Rows are scoped to the verified token subject -- there is no way to "
        "read another user's notifications."
    ),
    responses=error_responses(401, 403, 422),
)
async def list_notifications(
    actor: CurrentUserDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NotificationPage:
    return await service.list_notifications(session, actor, limit=limit, offset=offset)


@router.post(
    "/notifications/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark notifications read",
    description=(
        "Marks the given notification ids as read for the caller. Ids that "
        "do not belong to the caller, or are already read, are ignored -- the "
        "response does not reveal whether a foreign id exists."
    ),
    responses=error_responses(401, 403, 422),
)
async def mark_notifications_read(
    payload: MarkReadRequest,
    actor: CurrentUserDep,
    session: SessionDep,
) -> None:
    await service.mark_notifications_read(session, actor, payload.ids)
