"""What `record_action` puts in the log, without touching a database."""

import uuid
from typing import Any

import pytest

from app.core.logging import request_id_var
from app.modules.identity import service
from app.modules.identity.models import AuditAction


class FakeRepository:
    """Captures what would have been written."""

    def __init__(self, session: object) -> None:
        self.calls: list[dict[str, Any]] = []

    async def append(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return kwargs


async def _record(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> dict[str, Any]:
    calls: list[dict[str, Any]] = []

    class Capturing(FakeRepository):
        async def append(self, **inner: Any) -> dict[str, Any]:
            calls.append(inner)
            return inner

    monkeypatch.setattr(service, "AuditLogRepository", Capturing)
    await service.record_action(object(), **kwargs)  # type: ignore[arg-type]
    return calls[0]


async def test_records_the_action_value(monkeypatch: pytest.MonkeyPatch) -> None:
    call = await _record(monkeypatch, action=AuditAction.REPORT_REVEALED)

    assert call["action"] == "report.revealed"


async def test_target_id_is_stringified(monkeypatch: pytest.MonkeyPatch) -> None:
    target = uuid.uuid4()

    call = await _record(
        monkeypatch,
        action=AuditAction.REPORT_REVEALED,
        target_type="startup",
        target_id=target,
    )

    assert call["target_id"] == str(target)
    assert call["target_type"] == "startup"


async def test_system_actions_have_no_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Stripe webhook or scheduled job has no human behind it."""
    call = await _record(monkeypatch, action=AuditAction.SUBSCRIPTION_CHANGED)

    assert call["actor_id"] is None


async def test_request_id_is_attached_automatically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """So an audit row and the request's log lines can be tied together."""
    token = request_id_var.set("req-abc")
    try:
        call = await _record(monkeypatch, action=AuditAction.USER_SUSPENDED)
    finally:
        request_id_var.reset(token)

    assert call["details"]["request_id"] == "req-abc"


async def test_caller_details_are_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    token = request_id_var.set("req-abc")
    try:
        call = await _record(
            monkeypatch,
            action=AuditAction.USER_ROLE_CHANGED,
            details={"from": "founder", "to": "admin"},
        )
    finally:
        request_id_var.reset(token)

    assert call["details"] == {
        "from": "founder",
        "to": "admin",
        "request_id": "req-abc",
    }


async def test_caller_details_are_not_mutated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The caller's dict must not gain a request_id behind their back."""
    details: dict[str, Any] = {"from": "founder"}
    token = request_id_var.set("req-abc")
    try:
        await _record(
            monkeypatch, action=AuditAction.USER_ROLE_CHANGED, details=details
        )
    finally:
        request_id_var.reset(token)

    assert details == {"from": "founder"}


async def test_outside_a_request_there_is_no_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call = await _record(monkeypatch, action=AuditAction.PURCHASE_COMPLETED)

    assert "request_id" not in call["details"]


def test_every_action_is_namespaced() -> None:
    """`user.suspended`, not `suspended` -- the log is read by grep later."""
    for action in AuditAction:
        assert "." in action.value, f"{action.name} is not namespaced"
