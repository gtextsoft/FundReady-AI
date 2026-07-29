"""Typed exceptions, the error envelope, and the global exception handlers.

Every error response in the API is exactly one shape (CLAUDE.md section 6):

    {"error": {"code": "...", "message": "...", "details": {...}}}

`code` is a stable, documented string the mobile client can branch on --
`message` is human-facing prose and may change without notice, so clients must
never parse it.

Two rules this module exists to enforce:

* **No internals in a response.** An unhandled exception is logged in full
  server-side and answered with a generic `internal_error` plus the request id.
  Stack traces, driver messages, and connection strings never leave the process.
* **No echoing input back.** Validation failures report the field location and
  the reason, never the submitted value -- otherwise a rejected password or
  financial figure lands in the client's logs and our own.
"""

import logging
from typing import Any, ClassVar, Final

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.logging import get_request_id

logger = logging.getLogger(__name__)

# Spelled out rather than taken from `starlette.status`: those two constants
# were renamed upstream, and the old names now emit deprecation warnings while
# the new ones do not exist on older releases. The numbers are stable.
HTTP_413_PAYLOAD_TOO_LARGE: Final = 413
HTTP_422_UNPROCESSABLE: Final = 422


class ErrorCode:
    """Stable error codes. Documented in the README; never renamed in place."""

    UNAUTHENTICATED: Final = "unauthenticated"
    FORBIDDEN: Final = "forbidden"
    NOT_FOUND: Final = "not_found"
    METHOD_NOT_ALLOWED: Final = "method_not_allowed"
    CONFLICT: Final = "conflict"
    VALIDATION_ERROR: Final = "validation_error"
    PAYLOAD_TOO_LARGE: Final = "payload_too_large"
    RATE_LIMITED: Final = "rate_limited"
    INTERNAL_ERROR: Final = "internal_error"
    SERVICE_UNAVAILABLE: Final = "service_unavailable"


class ErrorBody(BaseModel):
    """The body of an error response."""

    code: str = Field(
        description="Stable, machine-readable error code. Branch on this.",
        examples=["forbidden"],
    )
    message: str = Field(
        description="Human-readable explanation. May change; do not parse.",
        examples=["You do not have access to this resource."],
    )
    details: dict[str, Any] | None = Field(
        default=None,
        description="Optional structured context. Never contains submitted values.",
    )


class ErrorEnvelope(BaseModel):
    """The one and only error response shape in this API."""

    error: ErrorBody


# ---------------------------------------------------------------------------
# Typed exceptions
# ---------------------------------------------------------------------------


class AppError(Exception):
    """Base class for every error this application raises deliberately."""

    code: ClassVar[str] = ErrorCode.INTERNAL_ERROR
    status_code: ClassVar[int] = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_message: ClassVar[str] = "Something went wrong."

    def __init__(
        self,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)


class UnauthenticatedError(AppError):
    """401 -- missing, invalid, or expired token. The client should refresh."""

    code = ErrorCode.UNAUTHENTICATED
    status_code = status.HTTP_401_UNAUTHORIZED
    default_message = "Authentication is required."


class ForbiddenError(AppError):
    """403 -- authenticated but not permitted. The client must not retry."""

    code = ErrorCode.FORBIDDEN
    status_code = status.HTTP_403_FORBIDDEN
    default_message = "You do not have access to this resource."


class NotFoundError(AppError):
    """404 -- absent, or hidden from this caller.

    Deliberately indistinguishable from "exists but is not yours": returning
    403 for another tenant's id would confirm that the id exists (AUTH.md
    section 6).
    """

    code = ErrorCode.NOT_FOUND
    status_code = status.HTTP_404_NOT_FOUND
    default_message = "Resource not found."


class ConflictError(AppError):
    """409 -- the request conflicts with current state."""

    code = ErrorCode.CONFLICT
    status_code = status.HTTP_409_CONFLICT
    default_message = "The request conflicts with the current state."


class InvalidRequestError(AppError):
    """422 -- semantically invalid request the schema could not reject."""

    code = ErrorCode.VALIDATION_ERROR
    status_code = HTTP_422_UNPROCESSABLE
    default_message = "The request is invalid."


class RateLimitedError(AppError):
    """429 -- too many requests."""

    code = ErrorCode.RATE_LIMITED
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_message = "Too many requests. Try again later."


class ConfigurationError(AppError):
    """500 -- the service is misconfigured. Never exposes which setting."""

    code = ErrorCode.INTERNAL_ERROR
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_message = "The service is not configured correctly."


class ServiceUnavailableError(AppError):
    """503 -- a dependency is unavailable."""

    code = ErrorCode.SERVICE_UNAVAILABLE
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_message = "The service is temporarily unavailable."


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_STATUS_TO_CODE: Final[dict[int, str]] = {
    status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHENTICATED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
    status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
    HTTP_413_PAYLOAD_TOO_LARGE: ErrorCode.PAYLOAD_TOO_LARGE,
    HTTP_422_UNPROCESSABLE: ErrorCode.VALIDATION_ERROR,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
    status.HTTP_503_SERVICE_UNAVAILABLE: ErrorCode.SERVICE_UNAVAILABLE,
}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Render the error envelope."""
    body = ErrorEnvelope(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", exclude_none=True),
        headers=headers,
    )


async def app_error_handler(request: Request, exc: Exception) -> Response:
    """Render a deliberately raised `AppError`."""
    assert isinstance(exc, AppError)  # noqa: S101 - registered for this type only
    logger.info(
        "request failed",
        extra={
            "context": {
                "code": exc.code,
                "status": exc.status_code,
                "path": request.url.path,
                "method": request.method,
            }
        },
    )
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


async def http_exception_handler(_request: Request, exc: Exception) -> Response:
    """Render Starlette's own `HTTPException` (404s, 405s) in our envelope."""
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    detail = exc.detail if isinstance(exc.detail, str) else ""
    message = detail or "Request failed."

    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        # Do not pass a 5xx detail string through; it may carry internals.
        message = "Something went wrong."

    headers = dict(exc.headers) if exc.headers else None
    return error_response(exc.status_code, code, message, headers=headers)


async def validation_exception_handler(_request: Request, exc: Exception) -> Response:
    """Render a schema validation failure.

    Reports where and why each field failed, and never what was submitted --
    `input` and `ctx` from pydantic are dropped on purpose so a rejected
    password or financial figure is not echoed back or logged.
    """
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    fields = [
        {
            "field": ".".join(str(part) for part in error["loc"]),
            "reason": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return error_response(
        HTTP_422_UNPROCESSABLE,
        ErrorCode.VALIDATION_ERROR,
        "The request failed validation.",
        details={"fields": fields},
    )


async def unhandled_exception_handler(request: Request, _exc: Exception) -> Response:
    """Last resort: log everything, reveal nothing.

    The traceback goes to the logs; the caller gets a generic message and the
    request id, which is enough to correlate a support report with a log line.
    """
    logger.exception(
        "unhandled exception",
        extra={"context": {"path": request.url.path, "method": request.method}},
    )
    request_id = get_request_id()
    return error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorCode.INTERNAL_ERROR,
        "Something went wrong.",
        details={"request_id": request_id} if request_id else None,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire every handler so no code path can return a non-enveloped error."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries, so every documented error shows its shape.

    Used on routes to satisfy CLAUDE.md section 6: every endpoint documents all
    of its error codes.
    """
    return {
        code: {
            "model": ErrorEnvelope,
            "description": _STATUS_TO_CODE.get(code, ErrorCode.INTERNAL_ERROR),
        }
        for code in codes
    }
