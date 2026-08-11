"""Notifications request/response schemas (T5.3).

Layer: **schemas** (ARCHITECTURE.md section 3) -- Pydantic request and response
models. Unknown or extra fields are rejected.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["MarkReadRequest", "NotificationPage", "NotificationResponse"]


class NotificationResponse(BaseModel):
    """One in-app notification, as the recipient sees it."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "id": "5f9b1c1e-6f5a-4c3b-9a1f-2d4e6a8c0b12",
                "kind": "task_assigned",
                "title": "New readiness task",
                "body": "Publish a 12-month cash forecast.",
                "payload": {"task_id": "0b6f0f2a-1c2d-4e5f-8a9b-0c1d2e3f4a5b"},
                "read_at": None,
                "created_at": "2026-08-11T08:00:00Z",
            }
        },
    )

    id: uuid.UUID
    kind: str = Field(description="Stable event type, e.g. `task_assigned`.")
    title: str
    body: str
    payload: dict[str, Any] = Field(
        description="Deep-link ids and other non-display context for the client."
    )
    read_at: datetime | None = Field(
        description="When the recipient marked it read, or `null` if unread."
    )
    created_at: datetime


class NotificationPage(BaseModel):
    """One page of notifications.

    Same `items`/`total`/`limit`/`offset` shape as readiness and discovery
    lists (`CLAUDE.md` section 6).
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {"items": [], "total": 0, "limit": 50, "offset": 0}
        },
    )

    items: list[NotificationResponse]
    total: int = Field(description="Total for this user, ignoring pagination.")
    limit: int
    offset: int


class MarkReadRequest(BaseModel):
    """Ids to mark read. Unknown or foreign ids are ignored."""

    model_config = ConfigDict(extra="forbid")

    ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Notification ids belonging to the caller.",
    )
