"""Identity business logic.

Layer: **service** (ARCHITECTURE.md section 3) -- business logic and
orchestration. Performs authorization and ownership checks (AUTH.md sections
5-6), calls this module's `repository`, `app.ai`, and other modules' public
service functions only (never their internals). Enqueues background jobs.
Selects the tier serializer for every response carrying report data
(DECISIONS.md D8).

`record_action` is this module's public entry point for the audit log. Other
modules call it -- brokerage when a full report is revealed, commerce on a
purchase, and so on -- rather than reaching for the repository themselves.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_request_id
from app.modules.identity.models import AuditAction, AuditLog
from app.modules.identity.repository import AuditLogRepository


async def record_action(
    session: AsyncSession,
    action: AuditAction,
    *,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Append one entry to the immutable audit log.

    The current request id is attached automatically, so an audit row and the
    log lines from the same request can be tied together later without anyone
    remembering to pass it.

    Callers must not put secrets, tokens, or document contents in `details` --
    the audit log is retained indefinitely and cannot be edited afterwards
    (CLAUDE.md section 4).
    """
    payload = dict(details or {})

    request_id = get_request_id()
    if request_id is not None:
        payload.setdefault("request_id", request_id)

    return await AuditLogRepository(session).append(
        action=action.value,
        actor_id=actor_id,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=payload,
    )
