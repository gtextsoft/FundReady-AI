"""Smoke test: the application imports, boots, and produces a valid contract.

The OpenAPI document is the deliverable the mobile developer builds against
(DECISIONS.md D1), so a build failure here is a broken contract, not just a
broken import.
"""

import importlib
import pkgutil

import app
from app.main import API_V1_PREFIX
from app.main import app as fastapi_app


def test_every_module_imports() -> None:
    """Every module in the package imports cleanly (T0.1 acceptance bar)."""
    for module in pkgutil.walk_packages(app.__path__, f"{app.__name__}."):
        importlib.import_module(module.name)


def test_app_metadata() -> None:
    assert fastapi_app.title == "FundReady API"
    assert fastapi_app.version == app.__version__


def test_api_is_versioned() -> None:
    """Every documented resource lives under /v1 (CLAUDE.md section 6).

    Asserted against the OpenAPI document rather than the route table: the
    document is the contract the mobile developer builds against, and the route
    table also holds internal container objects with no meaningful path.
    """
    assert API_V1_PREFIX == "/v1"

    paths = fastapi_app.openapi()["paths"]
    assert paths, "expected at least one documented endpoint"
    for path in paths:
        assert path.startswith(API_V1_PREFIX), f"unversioned route: {path}"


def test_openapi_document_builds() -> None:
    schema = fastapi_app.openapi()

    assert schema["info"]["title"] == "FundReady API"
    assert schema["info"]["version"] == app.__version__
    assert "paths" in schema
