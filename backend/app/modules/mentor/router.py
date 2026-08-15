"""Founder mentor HTTP endpoints (T3.7)."""

import json
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

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


@router.post(
    "/startups/{startup_id}/mentor/chat/stream",
    summary="Stream a mentor reply",
    description=(
        "Same grounding and access rules as `POST .../mentor/chat`. "
        "Responds with `text/event-stream`: `delta` events carry `{text}`, "
        "then a `done` event carries `{reply, citations}`."
    ),
    responses=error_responses(401, 403, 404, 422),
)
async def mentor_chat_stream(
    startup_id: uuid.UUID,
    payload: MentorChatRequest,
    actor: FounderWithAccess,
    session: SessionDep,
) -> StreamingResponse:
    async def events():
        async for kind, data in service.chat_stream(
            session,
            actor,
            startup_id,
            message=payload.message,
            history=payload.history,
        ):
            yield f"event: {kind}\ndata: {json.dumps(data)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
