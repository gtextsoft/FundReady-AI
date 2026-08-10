"""Error reporting reaches Sentry, and founder data does not.

`core/monitoring.py` shipped with a docstring saying it was "called from both
entry points -- the API's lifespan and the worker's `main`". Only the worker
ever called it, so the process handling every request reported nothing, in the
commit whose stated purpose was adding error reporting. Nothing caught it
because no test asserted the wiring.

The rest of this file is `CLAUDE.md` section 4: what Sentry is allowed to
receive. `send_default_pii=False` is the setting people reach for and it is not
the one that matters here -- it drops request bodies and headers, and says
nothing about the local variables of a captured stack frame. The audit worker's
failure path has the founder's full financial profile bound to `snapshot` at the
moment it raises.
"""

from typing import Any

import pytest

from app.core.config import get_settings
from app.core.logging import REDACTED
from app.core.monitoring import _scrub, init_sentry  # noqa: PLC2701


def test_the_api_lifespan_starts_error_reporting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression: only the worker's `main` ever called this."""
    import app.main as main

    calls: list[str] = []
    monkeypatch.setattr(
        main, "init_sentry", lambda _settings, *, component: calls.append(component)
    )

    async def no_dispose() -> None:
        """The engine is shared with the rest of the session; leave it alone."""

    monkeypatch.setattr(main, "dispose_engine", no_dispose)

    async def run() -> None:
        async with main.lifespan(main.app):
            pass

    import asyncio

    asyncio.run(run())

    assert calls == ["api"], "the API process must report errors, not just the worker"


def test_error_reporting_stays_off_without_a_dsn() -> None:
    """CI and development have no DSN, and must not ship test data anywhere."""
    get_settings.cache_clear()
    try:
        assert init_sentry(get_settings(), component="test") is False
    finally:
        get_settings.cache_clear()


class TestWhatSentryMayReceive:
    """`before_send` is the last line of defence; assert it on a real event shape."""

    def test_an_api_key_in_an_exception_message_is_redacted(self) -> None:
        event: Any = {
            "exception": {
                "values": [
                    {"type": "AuthenticationError", "value": "bad key sk-ant-abc123def"}
                ]
            }
        }

        scrubbed: Any = _scrub(event, {})

        value = scrubbed["exception"]["values"][0]["value"]
        assert "sk-ant-abc123def" not in value
        assert REDACTED in value

    def test_database_credentials_in_an_exception_message_are_redacted(self) -> None:
        event: Any = {
            "exception": {
                "values": [
                    {
                        "type": "OperationalError",
                        "value": "could not connect to "
                        "postgresql://svc:s3cr3tpw@ep-cool.neon.tech:5432/main",
                    }
                ]
            }
        }

        scrubbed: Any = _scrub(event, {})

        assert "s3cr3tpw" not in scrubbed["exception"]["values"][0]["value"]

    def test_a_log_message_is_redacted(self) -> None:
        event: Any = {"logentry": {"message": "retrying with Bearer eyJabc.def.ghi"}}

        scrubbed: Any = _scrub(event, {})

        assert "eyJabc.def.ghi" not in scrubbed["logentry"]["message"]

    def test_an_event_carrying_neither_field_is_passed_through(self) -> None:
        """A transaction event has no exception and no logentry."""
        event: Any = {"type": "transaction", "transaction": "GET /v1/health"}

        assert _scrub(event, {}) == event


def test_stack_locals_are_not_collected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The setting that actually keeps the founder's figures out of Sentry.

    Asserted on the kwargs handed to `sentry_sdk.init` rather than by capturing
    an event, because the value being wrong is a silent default -- the SDK ships
    `include_local_variables=True`, and `send_default_pii=False` does not imply
    it. `workers.tasks.run_audit_async` has revenue, costs, and cash on hand
    bound to `snapshot` in the frame that raises.
    """
    import sentry_sdk

    captured: dict[str, Any] = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(sentry_sdk, "set_tag", lambda *_args: None)
    monkeypatch.setenv("SENTRY_DSN", "https://public@o0.ingest.sentry.io/0")
    get_settings.cache_clear()

    try:
        assert init_sentry(get_settings(), component="test") is True
    finally:
        get_settings.cache_clear()

    assert captured["include_local_variables"] is False
    assert captured["send_default_pii"] is False
    assert captured["before_send"] is _scrub
