"""Golden Layer B — billed audit accuracy against the curated company set.

Layer A (determinism / offline scoring) lives in `tests/unit/test_golden_*.py`
and runs in CI. This module is **Layer B**: end-to-end calls against the live
Claude API that score how close the pipeline lands to hand-labelled verdicts
in `companies.json`.

It is skipped by default so CI never bills. To run locally / on a billed runner:

    pytest tests/golden/test_golden_accuracy.py -m billed \\
        --override-ini="addopts="

Requires `ANTHROPIC_API_KEY` and a working database. Do not enable this in the
default CI job.
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.billed,
    pytest.mark.skip(
        reason=(
            "Layer B billed accuracy — run explicitly with "
            "`pytest tests/golden/test_golden_accuracy.py -m billed` "
            "and ANTHROPIC_API_KEY set; never in default CI."
        )
    ),
]


def test_golden_accuracy_layer_b_placeholder() -> None:
    """Stub: wire live AiClient + companies.json expectations when billed.

    Intentionally empty so the marker / skip documentation is discoverable
    without calling the API. Replace the body with a real accuracy harness
    when a billed eval job is provisioned.
    """
    pytest.fail("unreachable: module is skipped by default")
