"""Every error leaves the API in one shape, and leaks nothing.

The envelope is part of the contract the mobile developer builds against
(CLAUDE.md section 6), so its shape is asserted rather than assumed. The
non-disclosure tests belong here too: an error response is the easiest place to
accidentally hand out a stack trace, a driver message, or a submitted password.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import (
    ConflictError,
    ErrorCode,
    ForbiddenError,
    NotFoundError,
    UnauthenticatedError,
    register_exception_handlers,
)
from app.core.logging import REQUEST_ID_HEADER, RequestContextMiddleware

SECRET_PASSWORD = "correct-horse-battery-staple"


class _Payload(BaseModel):
    email: str
    password: str
    amount_minor: int


@pytest.fixture
def failing_app() -> FastAPI:
    """An app that can produce every error path, wired like the real one."""
    test_app = FastAPI()
    test_app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(test_app)

    @test_app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("connection to postgresql://svc:s3cr3tpw@db.internal failed")

    @test_app.get("/unauthenticated")
    async def unauthenticated() -> None:
        raise UnauthenticatedError

    @test_app.get("/forbidden")
    async def forbidden() -> None:
        raise ForbiddenError

    @test_app.get("/missing")
    async def missing() -> None:
        raise NotFoundError

    @test_app.get("/conflict")
    async def conflict() -> None:
        raise ConflictError("Already submitted.", details={"audit_run_id": "abc"})

    @test_app.post("/submit")
    async def submit(payload: _Payload) -> dict[str, str]:
        return {"email": payload.email}

    return test_app


@pytest.fixture
def failing_client(failing_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(failing_app, raise_server_exceptions=False) as test_client:
        yield test_client


def _envelope(body: Any) -> dict[str, Any]:
    """Assert the envelope shape and return the error object."""
    assert set(body) == {"error"}, "an error response contains only `error`"
    error = body["error"]
    assert set(error) <= {"code", "message", "details"}
    assert isinstance(error["code"], str)
    assert isinstance(error["message"], str)
    return dict(error)


@pytest.mark.parametrize(
    ("path", "status_code", "code"),
    [
        ("/unauthenticated", 401, ErrorCode.UNAUTHENTICATED),
        ("/forbidden", 403, ErrorCode.FORBIDDEN),
        ("/missing", 404, ErrorCode.NOT_FOUND),
        ("/conflict", 409, ErrorCode.CONFLICT),
    ],
)
def test_typed_errors_use_the_envelope(
    failing_client: TestClient, path: str, status_code: int, code: str
) -> None:
    response = failing_client.get(path)

    assert response.status_code == status_code
    assert _envelope(response.json())["code"] == code


def test_details_are_passed_through(failing_client: TestClient) -> None:
    error = _envelope(failing_client.get("/conflict").json())

    assert error["details"] == {"audit_run_id": "abc"}


def test_unknown_route_uses_the_envelope(failing_client: TestClient) -> None:
    response = failing_client.get("/no-such-route")

    assert response.status_code == 404
    assert _envelope(response.json())["code"] == ErrorCode.NOT_FOUND


def test_method_not_allowed_uses_the_envelope(failing_client: TestClient) -> None:
    response = failing_client.post("/forbidden")

    assert response.status_code == 405
    assert _envelope(response.json())["code"] == ErrorCode.METHOD_NOT_ALLOWED


class TestValidationErrors:
    def test_reports_field_and_reason(self, failing_client: TestClient) -> None:
        response = failing_client.post("/submit", json={"email": "a@b.test"})

        assert response.status_code == 422
        error = _envelope(response.json())
        assert error["code"] == ErrorCode.VALIDATION_ERROR

        fields = {item["field"] for item in error["details"]["fields"]}
        assert "body.password" in fields
        assert "body.amount_minor" in fields

    def test_never_echoes_the_submitted_value(self, failing_client: TestClient) -> None:
        """A rejected password must not come back in the response body."""
        response = failing_client.post(
            "/submit",
            json={
                "email": "a@b.test",
                "password": SECRET_PASSWORD,
                "amount_minor": "not-a-number",
            },
        )

        assert response.status_code == 422
        assert SECRET_PASSWORD not in response.text
        assert "not-a-number" not in response.text


class TestUnhandledExceptions:
    def test_returns_generic_internal_error(self, failing_client: TestClient) -> None:
        response = failing_client.get("/boom")

        assert response.status_code == 500
        error = _envelope(response.json())
        assert error["code"] == ErrorCode.INTERNAL_ERROR
        assert error["message"] == "Something went wrong."

    def test_leaks_no_internals(self, failing_client: TestClient) -> None:
        """No traceback, no exception text, no connection string."""
        body = failing_client.get("/boom").text

        for leak in (
            "RuntimeError",
            "Traceback",
            "s3cr3tpw",
            "db.internal",
            "postgresql://",
            __file__,
        ):
            assert leak not in body

    def test_includes_the_request_id_for_correlation(
        self, failing_client: TestClient
    ) -> None:
        response = failing_client.get("/boom")

        request_id = response.headers[REQUEST_ID_HEADER]
        assert _envelope(response.json())["details"]["request_id"] == request_id


def test_real_app_404_uses_the_envelope(client: TestClient) -> None:
    """The wiring holds on the actual application, not just the fixture."""
    response = client.get("/v1/does-not-exist")

    assert response.status_code == 404
    assert _envelope(response.json())["code"] == ErrorCode.NOT_FOUND
