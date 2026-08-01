"""`CLIENTS.md` must keep describing the API that actually exists.

A hand-written integration guide rots silently: an endpoint gets renamed, the
guide still names the old path, and the client developer debugs against a
document that has been wrong for weeks. That is worse than having no guide,
because it is trusted.

CI cannot check prose. It *can* check that every path and every enum value the
guide names still exists, which catches the renames and removals that cause the
worst confusion. Paths are compared with their parameter names normalised away
(`{id}` vs `{user_id}`) so the guide can stay readable -- this asserts the route
still exists, not that it is spelled identically.
"""

import re
from pathlib import Path

import pytest

from app.main import app

GUIDE = Path(__file__).resolve().parents[2] / "CLIENTS.md"


def _normalise(path: str) -> str:
    """`/v1/users/{user_id}` and `/v1/users/{id}` compare equal."""
    return re.sub(r"\{[^}]*\}", "{}", path.rstrip("/"))


@pytest.fixture(scope="module")
def spec() -> dict:
    return app.openapi()


@pytest.fixture(scope="module")
def guide() -> str:
    return GUIDE.read_text(encoding="utf-8")


def test_the_guide_exists(guide: str) -> None:
    assert len(guide) > 2000, "CLIENTS.md is the client contract, not a stub"


def test_every_path_named_in_the_guide_exists(spec: dict, guide: str) -> None:
    live = {_normalise(p) for p in spec["paths"]}
    # Only `/v1/...` tokens inside backticks -- prose mentioning a path in
    # passing should not be load-bearing.
    named = {
        _normalise(m)
        for m in re.findall(r"`[A-Z]+ (/v1/[^`\s]*)`|`(/v1/[^`\s]*)`", guide)
        for m in [next(filter(None, m if isinstance(m, tuple) else (m,)), "")]
        if m
    }

    assert named, "no paths found -- the extraction regex has drifted"
    assert named <= live, (
        f"CLIENTS.md names paths that no longer exist: {sorted(named - live)}"
    )


def test_every_enum_value_in_the_guide_is_real(spec: dict, guide: str) -> None:
    """The enum table is what clients switch on, so a dropped value is a bug."""
    schemas = spec["components"]["schemas"]

    checked = 0
    for name, schema in schemas.items():
        if "enum" not in schema:
            continue
        row = re.search(rf"^\| `{re.escape(name)}` \| (.+?) \|$", guide, re.M)
        if row is None:
            continue
        documented = set(re.findall(r"`([^`]+)`", row.group(1)))
        live = set(schema["enum"])

        assert documented <= live, (
            f"{name}: guide documents values that no longer exist: "
            f"{sorted(documented - live)}"
        )
        assert live <= documented, (
            f"{name}: new values are undocumented, so a client will not handle "
            f"them: {sorted(live - documented)}"
        )
        checked += 1

    assert checked >= 8, f"only {checked} enum tables matched -- table format drifted"


def test_the_exported_spec_is_current(spec: dict) -> None:
    """`docs/openapi.json` is committed so clients can codegen without a server.

    A stale export is worse than none: it generates a client against endpoints
    that have moved. Regenerate with `python scripts/export_openapi.py`.
    """
    import json

    exported = GUIDE.parent / "docs" / "openapi.json"
    assert exported.exists(), "docs/openapi.json is missing -- regenerate it"

    on_disk = json.loads(exported.read_text(encoding="utf-8"))
    assert on_disk["paths"].keys() == spec["paths"].keys(), (
        "docs/openapi.json is stale: "
        f"added={sorted(spec['paths'].keys() - on_disk['paths'].keys())} "
        f"removed={sorted(on_disk['paths'].keys() - spec['paths'].keys())}"
    )
    assert on_disk["components"]["schemas"].keys() == (
        spec["components"]["schemas"].keys()
    ), "docs/openapi.json is stale: the schema set changed"


def test_the_documented_error_codes_are_the_real_ones(guide: str) -> None:
    """Clients branch on `code`, so this table is part of the contract."""
    from app.core.errors import ErrorCode

    live = {
        v
        for k, v in vars(ErrorCode).items()
        if not k.startswith("_") and isinstance(v, str)
    }
    documented = set(re.findall(r"^\| `([a-z_]+)` \| \d{3} \|", guide, re.M))

    assert documented, "the error-code table is missing or reformatted"
    assert documented <= live, (
        f"CLIENTS.md documents codes the API cannot emit: {sorted(documented - live)}"
    )
