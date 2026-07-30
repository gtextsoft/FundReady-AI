"""The liveness endpoint and its contract."""

from fastapi.testclient import TestClient

from app import __version__
from app.core.logging import REQUEST_ID_HEADER


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": __version__,
        "environment": "development",
    }


def test_health_requires_no_authentication(client: TestClient) -> None:
    """A load balancer cannot present a token."""
    assert client.get("/v1/health").status_code == 200


def test_health_is_versioned(client: TestClient) -> None:
    assert client.get("/health").status_code == 404


def test_response_carries_a_request_id(client: TestClient) -> None:
    response = client.get("/v1/health")

    assert response.headers[REQUEST_ID_HEADER]


def test_client_request_id_is_echoed(client: TestClient) -> None:
    """A mobile client can correlate its logs with ours."""
    response = client.get("/v1/health", headers={REQUEST_ID_HEADER: "mobile-abc-123"})

    assert response.headers[REQUEST_ID_HEADER] == "mobile-abc-123"


def test_hostile_request_id_is_not_reflected(client: TestClient) -> None:
    """An unvalidated client string must never be echoed into a header."""
    response = client.get(
        "/v1/health",
        headers={REQUEST_ID_HEADER: "abc <script>alert(1)</script>"},
    )

    assert response.headers[REQUEST_ID_HEADER] != "abc <script>alert(1)</script>"
    assert "<script>" not in response.headers[REQUEST_ID_HEADER]


def test_health_is_documented_in_openapi(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "/v1/health" in schema["paths"]
    assert schema["paths"]["/v1/health"]["get"]["summary"] == "Liveness check"
