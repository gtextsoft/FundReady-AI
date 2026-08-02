"""T2.8: the idempotency fingerprint and the run lifecycle enum.

`input_fingerprint` is the whole idempotency guarantee (DECISIONS.md D14). If it
is unstable, a founder is billed twice for one audit; if it is over-stable, a
founder who fixes their data gets the stale verdict back. Both failures are
silent, so the properties are tested directly rather than through the pipeline.
"""

from datetime import UTC, datetime
from decimal import Decimal

from app.modules.audit.runs import AuditStatus, input_fingerprint

PROFILE = {"monthly_revenue_minor": 4_100_000, "team_size": 6}


def _fp(**overrides: object) -> str:
    kwargs: dict = {"profile_fields": PROFILE, "rubric_version": "v1"}
    kwargs.update(overrides)
    return input_fingerprint(**kwargs)


# ---------------------------------------------------------------------------
# Stable: the same audit must not be paid for twice
# ---------------------------------------------------------------------------


def test_the_same_inputs_always_hash_the_same() -> None:
    assert len({_fp() for _ in range(10)}) == 1


def test_dict_insertion_order_does_not_change_the_hash() -> None:
    """Python preserves insertion order, so a profile assembled by a different
    code path would otherwise re-run a paid audit for identical data."""
    reversed_profile = dict(reversed(list(PROFILE.items())))

    assert list(reversed_profile) != list(PROFILE), "the fixture must differ in order"
    assert _fp(profile_fields=reversed_profile) == _fp()


def test_document_order_does_not_change_the_hash() -> None:
    keys = ["deck.pdf", "accounts.xlsx"]

    assert _fp(document_keys=keys) == _fp(document_keys=list(reversed(keys)))


def test_values_that_are_not_json_native_do_not_raise() -> None:
    """Money is `Decimal` and timestamps are `datetime` throughout the codebase.

    Coercing money to `float` to serialise it would let two distinct amounts
    collide, so `default=str` is what keeps the digest both possible and exact.
    """
    fingerprint = _fp(
        profile_fields={
            "gross_margin_percent": Decimal("42.5000"),
            "as_of": datetime(2026, 8, 1, tzinfo=UTC),
        }
    )

    assert len(fingerprint) == 64


# ---------------------------------------------------------------------------
# Sensitive: anything that changes the verdict must change the fingerprint
# ---------------------------------------------------------------------------


def test_a_changed_profile_value_changes_the_hash() -> None:
    assert _fp(profile_fields={**PROFILE, "team_size": 7}) != _fp()


def test_a_new_rubric_version_changes_the_hash() -> None:
    """D12: a new rubric is a different audit of identical data, so it must
    produce a new run rather than hand back a verdict formed under old rules."""
    assert _fp(rubric_version="v2") != _fp()


def test_adding_a_document_changes_the_hash() -> None:
    """Guards the T2.4a seam.

    Documents do not reach the audit yet, but once they do, a founder who
    uploads the missing financials and re-runs must not be handed back the
    pre-upload verdict. That regression would look exactly like the caching
    working correctly.
    """
    assert _fp(document_keys=["accounts.xlsx"]) != _fp(document_keys=[])


def test_a_removed_document_changes_the_hash() -> None:
    assert _fp(document_keys=["a.pdf", "b.pdf"]) != _fp(document_keys=["a.pdf"])


def test_two_different_profiles_do_not_collide() -> None:
    assert _fp(profile_fields={"a": 1}) != _fp(profile_fields={"b": 1})


def test_a_value_moving_between_fields_changes_the_hash() -> None:
    """`{"a": 1, "b": 2}` and `{"a": 2, "b": 1}` must not flatten to one digest."""
    assert _fp(profile_fields={"a": 1, "b": 2}) != _fp(profile_fields={"a": 2, "b": 1})


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_exactly_two_statuses_are_terminal() -> None:
    """Clients poll this enum and need to know when to stop (CLIENTS.md)."""
    terminal = {AuditStatus.SUCCEEDED, AuditStatus.FAILED}
    pending = {AuditStatus.QUEUED, AuditStatus.RUNNING}

    assert terminal | pending == set(AuditStatus)
    assert not terminal & pending


def test_status_values_are_the_documented_strings() -> None:
    assert [s.value for s in AuditStatus] == [
        "queued",
        "running",
        "succeeded",
        "failed",
    ]
