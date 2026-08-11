"""Have I Been Pwned range check (k-anonymity)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.core.errors import InvalidRequestError
from app.core.security import assert_password_not_breached


def _settings(**overrides: Any) -> Settings:
    return Settings(password_breach_check_enabled=True, **overrides)


@pytest.mark.asyncio
async def test_breached_password_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib

    password = "unique-test-password-for-hibp"
    digest = hashlib.sha1(password.encode()).hexdigest().upper()  # noqa: S324
    suffix = digest[5:]

    response = MagicMock()
    response.text = f"{suffix}:12\nDEADBEEF:1\n"
    response.raise_for_status = MagicMock()

    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr("httpx.AsyncClient", lambda **_: client)

    with pytest.raises(InvalidRequestError) as raised:
        await assert_password_not_breached(password, _settings())

    assert raised.value.details == {"reason": "breached_password"}


@pytest.mark.asyncio
async def test_clean_password_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    response = MagicMock()
    response.text = "DEADBEEF:1\n"
    response.raise_for_status = MagicMock()

    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr("httpx.AsyncClient", lambda **_: client)

    await assert_password_not_breached("a-fresh-unguessable-passphrase", _settings())


@pytest.mark.asyncio
async def test_network_failure_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**_: Any) -> Any:
        raise RuntimeError("dns down")

    monkeypatch.setattr("httpx.AsyncClient", _boom)

    await assert_password_not_breached("anything-long-enough", _settings())


@pytest.mark.asyncio
async def test_disabled_flag_skips_check(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def _should_not_run(**_: Any) -> Any:
        nonlocal called
        called = True
        raise AssertionError("HIBP must not be contacted when disabled")

    monkeypatch.setattr("httpx.AsyncClient", _should_not_run)

    await assert_password_not_breached(
        "anything-long-enough",
        Settings(password_breach_check_enabled=False),
    )
    assert called is False
