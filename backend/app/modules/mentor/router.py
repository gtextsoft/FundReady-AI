"""Founder mentor HTTP endpoints (T3.7)."""

import uuid

from fastapi import APIRouter

from app.core.deps import FounderWithAccess, SessionDep
from app.core.errors import error_responses
from app.modules.mentor import service
from app.modules.mentor.schemas import MentorChatRequest, MentorChatResponse

router = APIRouter(tags=["mentor"])


@router.post(
    "/startups/{startup_id}/mentor/chat",
    response_model=MentorChatResponse,
    summary="Chat with the AI mentor about your audit",
    description=(
        "Answers questions using **only** this startup's latest succeeded audit "
        "report, readiness tasks, and profile facts. Cross-tenant data is never "
        "retrieved, even when the message asks for it.\n\n"
        "Requires a succeeded audit — otherwise `422`. Uses the chat-tier model "
        "(DECISIONS.md D16)."
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def mentor_chat(
    startup_id: uuid.UUID,
    payload: MentorChatRequest,
    actor: FounderWithAccess,
    session: SessionDep,
) -> MentorChatResponse:
    return await service.chat(
        session,
        actor,
        startup_id,
        message=payload.message,
        history=payload.history,
    )
