"""Notification request/response schemas (T5.3)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.notifications.models import Notification, NotificationKind


class NotificationItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "id": "a1b2c3d4-0000-4000-8000-000000000001",
                "kind": "audit_ready",
                "title": "Your assessment is ready",
                "body": "Open FundReady to read the report.",
                "payload": {},
                "read_at": None,
                "created_at": "2026-08-15T12:00:00Z",
            }
        },
    )

    id: uuid.UUID
    kind: NotificationKind
    title: str
    body: str
    payload: dict[str, Any]
    read_at: datetime | None
    created_at: datetime

    @classmethod
    def of(cls, row: Notification) -> "NotificationItem":
        return cls(
            id=row.id,
            kind=row.kind,
            title=row.title,
            body=row.body,
            payload=row.payload or {},
            read_at=row.read_at,
            created_at=row.created_at,
        )


class NotificationPage(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {"items": [], "total": 0, "limit": 20, "offset": 0}
        },
    )

    items: list[NotificationItem]
    total: int
    limit: int
    offset: int


class MarkReadRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {"ids": ["a1b2c3d4-0000-4000-8000-000000000001"]}
        },
    )

    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
