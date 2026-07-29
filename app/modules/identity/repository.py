"""Identity data access.

Layer: **repository** (ARCHITECTURE.md section 3) -- database access only.
Queries in, models/data out. No business rules, no authorization decisions.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import AuditLog


class AuditLogRepository:
    """Append and read the audit log.

    **There is deliberately no update or delete method.** The database rejects
    both, but the absence of a callable is the first line of defence: code that
    cannot be written cannot be reviewed carelessly and merged.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        action: str,
        actor_id: uuid.UUID | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details or {},
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list_for_target(
        self, *, target_type: str, target_id: str, limit: int = 100
    ) -> Sequence[AuditLog]:
        statement = (
            select(AuditLog)
            .where(AuditLog.target_type == target_type, AuditLog.target_id == target_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return (await self._session.scalars(statement)).all()

    async def list_for_actor(
        self, *, actor_id: uuid.UUID, limit: int = 100
    ) -> Sequence[AuditLog]:
        statement = (
            select(AuditLog)
            .where(AuditLog.actor_id == actor_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return (await self._session.scalars(statement)).all()
