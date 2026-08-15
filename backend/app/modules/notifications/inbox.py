"""In-app notification writes. Callers never fail if this raises."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser
from app.modules.notifications.models import Notification, NotificationKind
from app.modules.notifications.schemas import NotificationItem, NotificationPage

logger = logging.getLogger(__name__)


async def notify(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    kind: str,
    title: str,
    body: str,
    payload: dict[str, Any] | None = None,
) -> None:
    session.add(
        Notification(
            user_id=user_id,
            kind=NotificationKind(kind),
            title=title,
            body=body,
            payload=payload or {},
        )
    )
    await session.flush()


async def list_for_user(
    session: AsyncSession,
    actor: CurrentUser,
    *,
    limit: int,
    offset: int,
) -> NotificationPage:
    total = int(
        await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == actor.id)
        )
        or 0
    )
    rows = list(
        await session.scalars(
            select(Notification)
            .where(Notification.user_id == actor.id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return NotificationPage(
        items=[NotificationItem.of(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


async def mark_read(
    session: AsyncSession, actor: CurrentUser, ids: list[uuid.UUID]
) -> None:
    if not ids:
        return
    await session.execute(
        update(Notification)
        .where(
            Notification.user_id == actor.id,
            Notification.id.in_(ids),
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
    )
