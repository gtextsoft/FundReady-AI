"""Structured application logging.

Logs are JSON on stdout, one object per line, each carrying the `request_id`
that also comes back to the caller in the `X-Request-ID` header -- so a support
report maps to a log line without the caller ever seeing internals.

CLAUDE.md section 4 bans secrets, tokens, and PII from logs. That ban is
enforced here by `RedactionFilter` rather than left to the discipline of every
future call site: anything shaped like an Authorization header, bearer token,
JWT, or provider API key is scrubbed before a record is ever formatted.
"""

import json
import logging
import re
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Final

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings

REQUEST_ID_HEADER: Final = "X-Request-ID"
REDACTED: Final = "[REDACTED]"

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Keys whose values are never safe to log, wherever they appear.
_SENSITIVE_KEYS: Final = (
    "authorization",
    "cookie",
    "set-cookie",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "api-key",
    "credential",
    "private_key",
)

_REDACTION_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    # `Authorization: Bearer x`, `x-api-key=y`, `"password": "z"`
    (
        re.compile(
            r"(?i)\b("
            r"authorization|cookie|set-cookie|x-api-key|api[_-]?key|"
            r"password|passwd|secret|token|credential|private[_-]?key"
            r")\b(\"?\s*[:=]\s*\"?)([^\s,;\"}]+)"
        ),
        r"\1\2" + REDACTED,
    ),
    # A bare bearer token anywhere in the message.
    (re.compile(r"(?i)\bbearer\s+[\w.\-+/=]+"), f"Bearer {REDACTED}"),
    # A JWT, which is what a leaked access token of ours looks like.
    (re.compile(r"\beyJ[\w-]{5,}\.[\w-]+\.[\w-]*"), REDACTED),
    # Provider key shapes: Stripe (sk_live_, whsec_), Anthropic (sk-ant-).
    (re.compile(r"(?i)\b(?:sk|pk|rk|whsec)[_-][\w-]{8,}"), REDACTED),
    # A Postgres URL carrying inline credentials.
    (
        re.compile(r"(?i)\b(postgres(?:ql)?(?:\+\w+)?://)[^\s:@]+:[^\s@]+@"),
        r"\1" + REDACTED + "@",
    ),
)


def redact(text: str) -> str:
    """Scrub anything secret-shaped from a string."""
    for pattern, replacement in _REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _redact_value(key: str, value: Any) -> Any:
    if key.lower() in _SENSITIVE_KEYS:
        return REDACTED
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: _redact_value(str(k), v) for k, v in value.items()}
    return value


class RedactionFilter(logging.Filter):
    """Strip secret-shaped content from every record before it is formatted."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Interpolate now so redaction also covers values passed as args.
        if record.args:
            record.msg = record.getMessage()
            record.args = None
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)

        context = getattr(record, "context", None)
        if isinstance(context, dict):
            record.context = {
                str(k): _redact_value(str(k), v) for k, v in context.items()
            }
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id

        context = getattr(record, "context", None)
        if isinstance(context, dict):
            payload["context"] = context

        if record.exc_info:
            # Server-side only. The traceback must never reach a response body
            # (see `core.errors.unhandled_exception_handler`).
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    """Install the JSON formatter and redaction filter on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())

    root = logging.getLogger()
    for existing in tuple(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(settings.log_level)

    # Let uvicorn's loggers flow through our handler instead of their own.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True


class RequestContextMiddleware:
    """Bind a request id to the log context and echo it back to the caller.

    An inbound `X-Request-ID` is honoured so a mobile client can correlate its
    own logs with ours; otherwise one is generated.

    Written as raw ASGI, and it converts unhandled exceptions itself, because
    Starlette's `ServerErrorMiddleware` sits *outside* every user middleware.
    If the 500 were left to it, the response would escape without the
    `X-Request-ID` header and the request-id context would already have been
    torn down -- leaving a support report with nothing to correlate on.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER, "").strip()
        # Never reflect an arbitrary client string back unvalidated.
        request_id = incoming if _is_safe_request_id(incoming) else str(uuid.uuid4())
        token = request_id_var.set(request_id)
        started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            if started:
                # Headers are already on the wire; nothing can be salvaged.
                raise
            # Imported here rather than at module scope: `core.errors` imports
            # this module for the request id, so a top-level import would be
            # circular. This path is rare enough for that to cost nothing.
            from app.core.errors import unhandled_exception_handler

            response = await unhandled_exception_handler(
                Request(scope, receive), _current_exception()
            )
            await response(scope, receive, send_with_request_id)
        finally:
            request_id_var.reset(token)


def _current_exception() -> Exception:
    """The exception currently being handled."""
    exc = sys.exc_info()[1]
    return exc if isinstance(exc, Exception) else RuntimeError("unknown error")


def _is_safe_request_id(value: str) -> bool:
    """Accept only a short, opaque, header-safe id."""
    if not value or len(value) > 64:
        return False
    return re.fullmatch(r"[\w.\-]+", value) is not None


def get_request_id() -> str | None:
    """The current request's id, if we are inside a request."""
    return request_id_var.get()
