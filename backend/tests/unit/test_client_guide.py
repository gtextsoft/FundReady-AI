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


def _named_paths(guide: str) -> set[str]:
    """Every `/v1/...` token the guide names inside backticks.

    Backticks only -- prose mentioning a path in passing should not be
    load-bearing in either direction.
    """
    return {
        _normalise(m)
        for m in re.findall(r"`[A-Z]+ (/v1/[^`\s]*)`|`(/v1/[^`\s]*)`", guide)
        for m in [next(filter(None, m if isinstance(m, tuple) else (m,)), "")]
        if m
    }


def test_every_path_named_in_the_guide_exists(spec: dict, guide: str) -> None:
    live = {_normalise(p) for p in spec["paths"]}
    named = _named_paths(guide)

    assert named, "no paths found -- the extraction regex has drifted"
    assert named <= live, (
        f"CLIENTS.md names paths that no longer exist: {sorted(named - live)}"
    )


def test_every_live_path_is_named_in_the_guide(spec: dict, guide: str) -> None:
    """The other direction, and the one that was missing.

    `test_every_path_named_in_the_guide_exists` asserts `named <= live`, so a
    documented path that vanishes is caught -- but a **new endpoint that is never
    documented passed silently**, which is the failure mode that actually
    happens: nobody forgets to remove a path, everybody forgets to add one.
    `CLAUDE.md` section 6 says every endpoint is documented; until this existed,
    nothing enforced it.
    """
    live = {_normalise(p) for p in spec["paths"]}
    named = _named_paths(guide)

    assert live <= named, (
        f"endpoints exist that CLIENTS.md does not document: {sorted(live - named)}"
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


def test_documented_status_codes_match_the_spec(spec: dict, guide: str) -> None:
    """The guide said `201` where the API returns `200`, and nothing caught it.

    A wrong success code is among the most expensive documentation errors
    possible: the client developer writes `if status == 201`, it never matches,
    and the bug looks like a server fault rather than a doc fault. Anywhere the
    guide writes `VERB /path → NNN`, that code must exist on that operation.
    """
    by_path = {
        _normalise(path): {
            verb: set(op.get("responses", {})) for verb, op in ops.items()
        }
        for path, ops in spec["paths"].items()
    }

    claims = re.findall(
        r"^\s*\d+\.\s+(GET|POST|PUT|PATCH|DELETE)\s+(/v1/\S+)\s+→\s+(\d{3})",
        guide,
        re.M,
    )
    assert claims, "no `VERB /path → NNN` claims found -- the guide format drifted"

    for verb, path, code in claims:
        operations = by_path.get(_normalise(path))
        assert operations is not None, f"{verb} {path}: path does not exist"

        declared = operations.get(verb.lower())
        assert declared is not None, f"{verb} {path}: verb not supported"
        assert code in declared, (
            f"CLIENTS.md says {verb} {path} returns {code}, "
            f"but the API declares {sorted(declared)}"
        )


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
