"""Secrets must not survive into a log line (CLAUDE.md section 4).

These are the tests that make the ban structural rather than a matter of
remembering. Each case is a string that has genuinely leaked into logs in real
systems.
"""

import json
import logging
import sys

import pytest

from app.core.logging import (
    REDACTED,
    JsonFormatter,
    RedactionFilter,
    redact,
    request_id_var,
)

SECRET_STRINGS = [
    pytest.param(
        "Authorization: Bearer eyJhbGciOi.payloadpart.signaturepart",
        "eyJhbGciOi.payloadpart.signaturepart",
        id="authorization-header",
    ),
    pytest.param(
        "calling stripe with sk_live_51H8xKfAbCdEfGhIjKl",
        "sk_live_51H8xKfAbCdEfGhIjKl",
        id="stripe-secret-key",
    ),
    pytest.param(
        "webhook whsec_9fJk2LmNoPqRsTuVwXyZ12345",
        "whsec_9fJk2LmNoPqRsTuVwXyZ12345",
        id="stripe-webhook-secret",
    ),
    pytest.param(
        'payload {"password": "hunter2horse"}',
        "hunter2horse",
        id="password-in-json",
    ),
    pytest.param(
        "api_key=ak_9182hfkdjshf7261",
        "ak_9182hfkdjshf7261",
        id="api-key-assignment",
    ),
    pytest.param(
        "connecting to postgresql://svc:s3cr3tpw@ep-cool-name.neon.tech:5432/main",
        "s3cr3tpw",
        id="database-url-credentials",
    ),
    pytest.param(
        "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdef",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdef",
        id="bare-jwt",
    ),
]


@pytest.mark.parametrize(("text", "secret"), SECRET_STRINGS)
def test_redact_removes_secret(text: str, secret: str) -> None:
    result = redact(text)

    assert secret not in result
    assert REDACTED in result


def _record(message: str, **kwargs: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=None,
        exc_info=None,
    )
    for key, value in kwargs.items():
        setattr(record, key, value)
    return record


@pytest.mark.parametrize(("text", "secret"), SECRET_STRINGS)
def test_filter_scrubs_the_record(text: str, secret: str) -> None:
    record = _record(text)

    assert RedactionFilter().filter(record) is True
    assert secret not in record.getMessage()


def test_filter_scrubs_interpolated_arguments() -> None:
    """A secret passed as a `%s` argument is still a secret."""
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="calling with %s",
        args=("Bearer eyJabc.def.ghi",),
        exc_info=None,
    )

    RedactionFilter().filter(record)

    assert "eyJabc.def.ghi" not in record.getMessage()


def test_filter_scrubs_structured_context_by_key_name() -> None:
    record = _record(
        "request",
        context={"authorization": "Bearer abc123", "path": "/v1/health"},
    )

    RedactionFilter().filter(record)

    context = record.context  # type: ignore[attr-defined]
    assert context["authorization"] == REDACTED
    assert context["path"] == "/v1/health"


def test_formatter_emits_json_with_request_id() -> None:
    token = request_id_var.set("req-123")
    try:
        payload = json.loads(JsonFormatter().format(_record("hello")))
    finally:
        request_id_var.reset(token)

    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "req-123"
    assert payload["timestamp"].endswith("+00:00")


def test_formatter_omits_request_id_outside_a_request() -> None:
    payload = json.loads(JsonFormatter().format(_record("startup")))

    assert "request_id" not in payload


def _record_with_exception(error: Exception) -> logging.LogRecord:
    """A record carrying a real traceback, the way `logger.exception` builds one."""
    try:
        raise error
    except type(error):
        return logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="audit failed",
            args=None,
            exc_info=sys.exc_info(),
        )


@pytest.mark.parametrize(("text", "secret"), SECRET_STRINGS)
def test_formatter_redacts_the_traceback(text: str, secret: str) -> None:
    """The traceback is built here and never passes through `RedactionFilter`.

    That filter scrubs `msg` and `context`; `formatException` reads `exc_info`,
    which it never touches. The two exceptions this project is most likely to
    log are exactly the two that carry a credential in their message -- psycopg
    quoting the Neon DSN, and the Anthropic SDK echoing the API key.
    """
    record = _record_with_exception(RuntimeError(text))
    RedactionFilter().filter(record)

    payload = json.loads(JsonFormatter().format(record))

    assert secret not in payload["exception"]
    assert REDACTED in payload["exception"]
