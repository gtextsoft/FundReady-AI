"""The OpenAPI document is the deliverable (DECISIONS.md D1).

A separate developer builds the mobile client from it, so gaps here are not
cosmetic -- they are the difference between an endpoint someone can call and one
they have to guess at. `CLAUDE.md` section 6 requires every endpoint to document
its purpose, auth requirement, schemas, **all** error codes, and at least one
example.

These assertions apply to every endpoint automatically, so a new route that
forgets its documentation fails here rather than reaching the mobile developer.
"""

from typing import Any

import pytest

from app.main import API_V1_PREFIX, app

DOC_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return app.openapi()


@pytest.fixture(scope="module")
def operations(spec: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [
        (f"{method.upper()} {path}", operation)
        for path, methods in spec["paths"].items()
        for method, operation in methods.items()
    ]


def test_there_are_endpoints_to_document(
    operations: list[tuple[str, dict[str, Any]]],
) -> None:
    assert operations


def test_every_endpoint_is_versioned(spec: dict[str, Any]) -> None:
    for path in spec["paths"]:
        assert path.startswith(API_V1_PREFIX), path


def test_every_endpoint_has_a_summary_and_description(
    operations: list[tuple[str, dict[str, Any]]],
) -> None:
    for name, operation in operations:
        assert operation.get("summary"), f"{name} has no summary"
        assert operation.get("description"), f"{name} has no description"


def test_a_bearer_security_scheme_is_published(spec: dict[str, Any]) -> None:
    """Without it, a client cannot tell how to authenticate at all."""
    schemes = spec.get("components", {}).get("securitySchemes", {})

    assert "Bearer" in schemes
    assert schemes["Bearer"]["scheme"] == "bearer"


def test_protected_endpoints_declare_their_security(
    operations: list[tuple[str, dict[str, Any]]],
) -> None:
    """Anything that can return 401 must say it needs a token."""
    for name, operation in operations:
        responses = operation.get("responses", {})
        if "401" in responses and "/auth/" not in name:
            assert operation.get("security"), f"{name} can 401 but declares no auth"


def test_every_error_response_uses_our_envelope(
    operations: list[tuple[str, dict[str, Any]]],
) -> None:
    """Regression: FastAPI auto-publishes a 422 with its own `HTTPValidationError`.

    That shape is not what this API returns. Any endpoint that takes a body or a
    path parameter but does not declare 422 explicitly gets FastAPI's model
    instead of ours, and the client codes against the wrong thing.
    """
    for name, operation in operations:
        for code, response in operation.get("responses", {}).items():
            if code[0] not in "45":
                continue
            schema = str(
                response.get("content", {})
                .get("application/json", {})
                .get("schema", {})
            )
            assert "ErrorEnvelope" in schema, (
                f"{name} documents {code} as {schema or '<no schema>'}, "
                "not the documented error envelope"
            )


def test_fastapis_own_validation_schema_is_absent(spec: dict[str, Any]) -> None:
    """If it reappears, some endpoint stopped declaring its 422."""
    assert "HTTPValidationError" not in spec["components"]["schemas"]


def test_every_request_and_response_model_has_an_example(
    spec: dict[str, Any],
) -> None:
    """`CLAUDE.md` section 6: at least one example per endpoint.

    Enums and the nested error body are exempt -- an example of a two-value
    enum documents nothing, and `ErrorBody` is shown through `ErrorEnvelope`.
    """
    exempt = {"ErrorBody"}
    for name, schema in spec["components"]["schemas"].items():
        if name in exempt or "enum" in schema:
            continue
        assert "examples" in schema or "example" in schema, (
            f"{name} publishes no example"
        )
