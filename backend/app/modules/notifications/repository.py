"""Notifications data access (T5.3).

Layer: **repository** (ARCHITECTURE.md section 3) -- database access only.
Queries in, models/data out. No business rules, no authorization decisions.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification

__all__ = ["NotificationRepository"]


class NotificationRepository:
    """Create, list, and mark notifications for a user."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        kind: str,
        title: str,
        body: str,
        payload: dict[str, Any] | None = None,
    ) -> Notification:
        row = Notification(
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            payload=payload if payload is not None else {},
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Notification], int]:
        """One page of this user's notifications, newest first, plus total."""
        base = select(Notification).where(Notification.user_id == user_id)
        total = await self._session.scalar(
            select(func.count()).select_from(base.subquery())
        )
        rows = await self._session.scalars(
            base.order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    async def mark_read(self, user_id: uuid.UUID, ids: Sequence[uuid.UUID]) -> int:
        """Mark the given ids read for this user only. Returns rows updated.

        Already-read rows are left alone. Ids that do not belong to `user_id`
        are ignored rather than raising -- the caller must not learn whether
        another user's notification id is real.
        """
        if not ids:
            return 0
        result = await self._session.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.id.in_(list(ids)),
                Notification.read_at.is_(None),
            )
            .values(read_at=datetime.now(UTC))
        )
        await self._session.flush()
        # `execute` is typed as Result; UPDATE returns CursorResult with rowcount.
        return int(cast("CursorResult[Any]", result).rowcount or 0)
