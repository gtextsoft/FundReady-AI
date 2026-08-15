"""Founder mentor chat — tenant-scoped retrieval + CHAT-tier completion (T3.7).

Retrieval is code-side: only the caller's own profile, latest succeeded audit
report, and readiness summary are assembled into CONTEXT. The model never
receives another startup's ids or data, even if the user asks for them.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from pydantic import ValidationError

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.caching import uncached_system
from app.ai.client import AiClient, ModelTier
from app.ai.guards import UNTRUSTED_RULE, fence
from app.core.config import get_settings
from app.core.errors import InvalidRequestError
from app.core.security import CurrentUser
from app.modules.audit import service as audit
from app.modules.audit.reports import founder_report
from app.modules.audit.runs import AuditStatus
from app.modules.intake import service as intake
from app.modules.mentor.ai_schema import MentorReplyOut
from app.modules.mentor.prompts import MENTOR_SYSTEM_V1
from app.modules.mentor.schemas import (
    ChatRole,
    ChatTurn,
    CitationKind,
    MentorChatResponse,
    MentorCitation,
)
from app.modules.readiness import service as readiness


async def _prepare_turn(
    session: AsyncSession,
    actor: CurrentUser,
    startup_id: uuid.UUID,
    message: str,
    history: list[ChatTurn],
) -> str:
    """Ownership-checked CONTEXT + fenced user payload for one mentor turn."""
    profile = await intake.get_profile(session, actor, startup_id)
    runs = await audit.list_audit_runs(session, actor, profile.id)
    succeeded = next((r for r in runs if r.status is AuditStatus.SUCCEEDED), None)
    if succeeded is None or succeeded.report is None:
        raise InvalidRequestError(
            "Run a successful audit before chatting with the mentor. "
            "There is no report to ground answers in yet."
        )

    stored = await audit.get_audit_report(session, actor, profile.id, succeeded.id)
    report = founder_report(stored)
    summary = await readiness.summarise_tasks(session, actor, profile.id)
    tasks_page = await readiness.list_tasks(
        session, actor, profile.id, limit=50, offset=0
    )

    task_rows, _ = tasks_page
    context = _build_context(
        profile_name=profile.name,
        sector=profile.sector,
        stage=profile.stage.value if profile.stage is not None else None,
        country=profile.country,
        report=report.model_dump(mode="json"),
        summary={
            "required_open": summary.required_open,
            "required_passed": summary.required_passed,
            "required_total": summary.required_total,
            "gate_cleared": summary.gate_cleared,
            "discoverable": summary.discoverable,
        },
        tasks=[
            {
                "dimension": t.dimension.value,
                "action": t.action,
                "status": t.status.value,
                "requirement": t.requirement.value,
                "is_priority": t.is_priority,
            }
            for t in task_rows
        ],
    )
    history_block = _format_history(history)
    user_payload = (
        f"CONTEXT:\n{context}\n\n"
        f"PRIOR_TURNS:\n{history_block}\n\n"
        f"FOUNDER_QUESTION:\n{message.strip()}"
    )
    return fence(user_payload, label="founder_mentor_turn").text


def _response_from_output(out: MentorReplyOut) -> MentorChatResponse:
    return MentorChatResponse(
        reply=out.reply,
        citations=[
            MentorCitation(kind=CitationKind(c.kind.value), ref=c.ref)
            for c in out.citations
        ],
    )


async def chat(
    session: AsyncSession,
    actor: CurrentUser,
    startup_id: uuid.UUID,
    message: str,
    history: list[ChatTurn],
    *,
    client: AiClient | None = None,
) -> MentorChatResponse:
    """Answer one mentor turn for the owner of `startup_id`."""
    fenced = await _prepare_turn(session, actor, startup_id, message, history)
    ai = client or AiClient(get_settings())
    result = await ai.complete(
        tier=ModelTier.CHAT,
        prompt=MENTOR_SYSTEM_V1,
        schema=MentorReplyOut,
        system=uncached_system(UNTRUSTED_RULE, MENTOR_SYSTEM_V1.text),
        messages=[{"role": "user", "content": fenced}],
        user_id=str(actor.id),
    )
    return _response_from_output(result.output)


async def chat_stream(
    session: AsyncSession,
    actor: CurrentUser,
    startup_id: uuid.UUID,
    message: str,
    history: list[ChatTurn],
    *,
    client: AiClient | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Same grounding as `chat`, yielded as SSE event payloads."""
    fenced = await _prepare_turn(session, actor, startup_id, message, history)
    ai = client or AiClient(get_settings())
    accumulated = ""
    async for chunk in ai.stream_text(
        tier=ModelTier.CHAT,
        schema=MentorReplyOut,
        system=uncached_system(UNTRUSTED_RULE, MENTOR_SYSTEM_V1.text),
        messages=[{"role": "user", "content": fenced}],
        user_id=str(actor.id),
    ):
        accumulated += chunk
        yield ("delta", {"text": chunk})
    try:
        out = MentorReplyOut.model_validate_json(accumulated)
        done = _response_from_output(out)
        yield (
            "done",
            {
                "reply": done.reply,
                "citations": [c.model_dump() for c in done.citations],
            },
        )
    except ValidationError:
        yield (
            "done",
            {
                "reply": accumulated.strip() or "The mentor could not finish that answer.",
                "citations": [],
            },
        )


def _build_context(
    *,
    profile_name: str | None,
    sector: str | None,
    stage: str | None,
    country: str | None,
    report: dict[str, Any],
    summary: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> str:
    payload = {
        "startup": {
            "name": profile_name,
            "sector": sector,
            "stage": stage,
            "country": country,
        },
        "report": report,
        "readiness_summary": summary,
        "tasks": tasks,
    }
    return json.dumps(payload, default=str)


def _format_history(history: list[ChatTurn]) -> str:
    if not history:
        return "(none)"
    lines: list[str] = []
    for turn in history[-10:]:
        role = "Founder" if turn.role is ChatRole.USER else "Mentor"
        lines.append(f"{role}: {turn.content.strip()}")
    return "\n".join(lines)
