"""T3.1: turning an audit's action plan into readiness tasks.

Two properties carry the weight here, and both are about a founder's
obligations rather than about data shapes.

**`required` means blocking, and it is arithmetic.** PRD section 4.2 says
blocking gaps become required tasks, and the gate in T3.6 tests exactly that
set -- so a classification that drifts from `synthesis`'s own notion of what
keeps a verdict off `ready` either obliges founders to do work that does not
matter or lets them skip work that does. The boundary case is tested directly,
because an off-by-one at `READY_THRESHOLD` is invisible in every other test.

**The same gap must be recognisable across audits.** A fingerprint that moves
between runs would make every re-audit mint a fresh set of tasks and strand the
founder's progress on the old ones. The tests below fix the ways it must not
move (whitespace, case) and the ways it must (dimension, wording).
"""

import pytest

from app.ai.schemas import Citation, DataSufficiency
from app.modules.audit.rubric.v1 import Dimension, DimensionScore
from app.modules.audit.synthesis import READY_THRESHOLD, synthesise
from app.modules.readiness.generation import (
    Requirement,
    TaskStatus,
    action_fingerprint,
    classify,
    plan_for_report,
    required_count,
)


def _score(
    dimension: Dimension,
    value: int = 80,
    *,
    sufficiency: DataSufficiency = DataSufficiency.SUFFICIENT,
    unmet: tuple[str, ...] = (),
) -> DimensionScore:
    citations = (
        []
        if sufficiency is DataSufficiency.INSUFFICIENT_DATA
        else [Citation(source_id="deck.pdf", quote="MRR of 4.1m NGN")]
    )
    return DimensionScore(
        dimension=dimension,
        score=value,
        rationale="because the evidence says so",
        sufficiency=sufficiency,
        citations=citations,
        unmet_criteria=list(unmet),
    )


# ---------------------------------------------------------------------------
# Required vs recommended is computed from the verdict's own threshold
# ---------------------------------------------------------------------------


def test_an_unscoreable_dimension_is_required() -> None:
    """`None` means the rubric returned insufficient_data.

    That trips synthesis's `thin` rule, which forces `provisional` no matter how
    strong everything else is -- so no amount of work elsewhere clears it.
    """
    assert classify(None) is Requirement.REQUIRED


def test_a_dimension_below_the_threshold_is_required() -> None:
    assert classify(READY_THRESHOLD - 1) is Requirement.REQUIRED


def test_a_dimension_exactly_at_the_threshold_is_not_required() -> None:
    """The verdict rule is `mean >= READY_THRESHOLD`.

    The boundary belongs on the passing side in both places. An off-by-one here
    would oblige a founder to work on a dimension the verdict already considers
    satisfactory, and nothing else in this suite would notice.
    """
    assert classify(READY_THRESHOLD) is Requirement.RECOMMENDED


def test_a_strong_dimension_is_recommended() -> None:
    assert classify(95) is Requirement.RECOMMENDED


@pytest.mark.parametrize("score", [0, 1, 42, READY_THRESHOLD - 1])
def test_everything_under_the_bar_blocks(score: int) -> None:
    assert classify(score) is Requirement.REQUIRED


@pytest.mark.parametrize("score", [READY_THRESHOLD, READY_THRESHOLD + 1, 100])
def test_nothing_at_or_over_the_bar_blocks(score: int) -> None:
    assert classify(score) is Requirement.RECOMMENDED


# ---------------------------------------------------------------------------
# The fingerprint is what survives a re-audit
# ---------------------------------------------------------------------------


def test_the_same_action_fingerprints_the_same() -> None:
    first = action_fingerprint(Dimension.TRACTION, "Publish a pricing page.")
    second = action_fingerprint(Dimension.TRACTION, "Publish a pricing page.")

    assert first == second


def test_whitespace_and_case_do_not_move_the_fingerprint() -> None:
    """The model rewrites each action every run.

    Identical instructions coming back with different spacing must reconcile to
    the one stored task, not insert a second copy beside it.
    """
    canonical = action_fingerprint(Dimension.TRACTION, "Publish a pricing page.")

    assert (
        action_fingerprint(Dimension.TRACTION, "  Publish a  pricing   page.  ")
        == canonical
    )
    assert (
        action_fingerprint(Dimension.TRACTION, "PUBLISH A PRICING PAGE.") == canonical
    )


def test_the_same_sentence_under_two_dimensions_is_two_tasks() -> None:
    """ "State your assumptions" is different work per dimension.

    Collapsing them would silently drop one of two obligations the founder is
    owed.
    """
    assert action_fingerprint(
        Dimension.TRACTION, "State your assumptions."
    ) != action_fingerprint(Dimension.MARKET_OPPORTUNITY, "State your assumptions.")


def test_different_wording_is_a_different_task() -> None:
    """A known limitation, asserted so nobody assumes otherwise.

    Semantic matching needs embeddings, which are still blocked on the provider
    decision. Until then a rephrased action produces a second task beside the
    first -- visible and dismissible, which is the safer failure than silently
    merging two genuinely different instructions.
    """
    assert action_fingerprint(
        Dimension.TRACTION, "Publish a pricing page."
    ) != action_fingerprint(Dimension.TRACTION, "Add pricing to the website.")


# ---------------------------------------------------------------------------
# A plan built from a real report
# ---------------------------------------------------------------------------


def test_a_weak_dimension_produces_required_tasks() -> None:
    report = synthesise(
        rubric_version="v1",
        scores=[
            _score(Dimension.TRACTION, 30, unmet=("Show month-on-month growth.",)),
            _score(Dimension.TEAM, 90, unmet=("Name a second technical hire.",)),
        ],
    )

    plan = plan_for_report(report)
    by_action = {task.action: task for task in plan}

    assert by_action["Show month-on-month growth."].requirement is Requirement.REQUIRED
    assert (
        by_action["Name a second technical hire."].requirement
        is Requirement.RECOMMENDED
    )


def test_an_unevidenced_dimension_produces_a_required_task() -> None:
    report = synthesise(
        rubric_version="v1",
        scores=[
            _score(
                Dimension.MARKET_OPPORTUNITY,
                0,
                sufficiency=DataSufficiency.INSUFFICIENT_DATA,
                unmet=("Size the market bottom-up.",),
            ),
        ],
    )

    (task,) = plan_for_report(report)

    assert task.requirement is Requirement.REQUIRED
    assert task.dimension_score is None


def test_the_plans_order_is_preserved() -> None:
    """`synthesis._action_plan` already ordered it worst-first.

    Re-sorting here would be a second copy of that rule, free to drift from it.
    """
    report = synthesise(
        rubric_version="v1",
        scores=[
            _score(Dimension.TEAM, 90, unmet=("Strong dimension action.",)),
            _score(Dimension.TRACTION, 20, unmet=("Weak dimension action.",)),
        ],
    )

    plan = plan_for_report(report)

    assert [task.action for task in plan] == [
        item.action for item in report.action_plan
    ]
    assert plan[0].action == "Weak dimension action."


def test_a_repeated_action_within_one_report_yields_one_task() -> None:
    """The storage layer keys on the fingerprint, so a duplicate would collide.

    Deduplicating here rather than letting the unique constraint reject the
    insert keeps the failure out of the worker's transaction, where it would
    have cost the whole audit.
    """
    report = synthesise(
        rubric_version="v1",
        scores=[
            _score(
                Dimension.TRACTION,
                30,
                unmet=("Show growth.", "show  GROWTH.", "Publish pricing."),
            ),
        ],
    )

    plan = plan_for_report(report)

    assert len(plan) == 2
    assert len({task.fingerprint for task in plan}) == 2


def test_priority_marking_is_carried_through() -> None:
    """The report singles out a short list; the task list has to agree with it."""
    report = synthesise(
        rubric_version="v1",
        scores=[
            _score(Dimension.TRACTION, 20, unmet=("Fix traction.",)),
            _score(Dimension.TEAM, 90, unmet=("Improve the team page.",)),
        ],
    )

    plan = plan_for_report(report)
    marked = {task.action for task in plan if task.is_priority}
    expected = {item.action for item in report.action_plan if item.is_priority}

    assert marked == expected
    assert "Fix traction." in marked


def test_required_count_counts_only_blocking_tasks() -> None:
    report = synthesise(
        rubric_version="v1",
        scores=[
            _score(Dimension.TRACTION, 20, unmet=("A.", "B.")),
            _score(Dimension.TEAM, 95, unmet=("C.",)),
        ],
    )

    plan = plan_for_report(report)

    assert required_count(plan) == 2


def test_a_report_with_no_unmet_criteria_generates_nothing() -> None:
    """A clean audit is not an error, and it must not invent busywork."""
    report = synthesise(
        rubric_version="v1",
        scores=[_score(Dimension.TRACTION, 95), _score(Dimension.TEAM, 95)],
    )

    assert plan_for_report(report) == ()


# ---------------------------------------------------------------------------
# The declared vocabulary
# ---------------------------------------------------------------------------


def test_the_status_vocabulary_covers_the_evidence_loop() -> None:
    """PRD section 4.2 grades evidence pass / fail / needs-more.

    Declared now because the column is a check-constrained enum: adding a value
    later is a migration on live rows plus a client release. This test is what
    stops one being dropped as "unused" before T3.5 arrives to use it.
    """
    assert {status.value for status in TaskStatus} == {
        "open",
        "submitted",
        "passed",
        "failed",
        "needs_more",
        "obsolete",
    }
