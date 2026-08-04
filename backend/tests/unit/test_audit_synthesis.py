"""T2.7: scores to verdicts, report, and action plan.

The first block is the one that matters. `CLAUDE.md` section 5 forbids a false
"fundable" on thin data, and that is a guarantee rather than a preference -- so
it is tested as an invariant across every shape of thin input, not with one
happy example.

The rest defends the distinction the rubric's `sufficiency` field exists to
protect: **"we could not assess this" is not "this is bad."** Collapsing them
would be invisible in the output and would tell a founder they failed an
assessment that never ran.
"""

from decimal import Decimal

import pytest

from app.ai.schemas import Citation, DataSufficiency
from app.modules.audit.consistency import Finding, FindingCode, Severity
from app.modules.audit.rubric.v1 import Dimension, DimensionScore, Scope, dimensions_for
from app.modules.audit.synthesis import (
    PRIORITY_DIMENSIONS,
    READY_THRESHOLD,
    VerdictLevel,
    synthesise,
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


def _all(value: int = 80, **kwargs: object) -> list[DimensionScore]:
    """Every dimension in both scopes, scored the same way."""
    keys = {spec.key for spec in dimensions_for(Scope.FUNDABILITY)} | {
        spec.key for spec in dimensions_for(Scope.SALEABILITY)
    }
    return [_score(key, value, **kwargs) for key in sorted(keys, key=lambda k: k.value)]  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Thin data never produces a confident verdict (CLAUDE.md Â§5)
# ---------------------------------------------------------------------------


def test_no_evidence_at_all_yields_insufficient_data_not_a_failure() -> None:
    report = synthesise(
        rubric_version="v1",
        scores=_all(0, sufficiency=DataSufficiency.INSUFFICIENT_DATA),
    )

    assert report.fundability.level is VerdictLevel.INSUFFICIENT_DATA
    assert report.fundability.score is None, "no score may be invented to fill the gap"
    assert report.saleability.level is VerdictLevel.INSUFFICIENT_DATA


def test_insufficient_data_is_never_worded_as_a_negative_result() -> None:
    """A founder must not read 'we could not assess you' as 'you failed'."""
    report = synthesise(
        rubric_version="v1",
        scores=_all(0, sufficiency=DataSufficiency.INSUFFICIENT_DATA),
    )

    rationale = report.fundability.rationale.lower()
    assert "not a negative result" in rationale
    assert "not fundable" not in rationale


def test_high_scores_on_thin_coverage_cannot_read_ready() -> None:
    """The dangerous case: everything submitted scores well, most is missing.

    A naive mean over the evidenced dimensions would say 95 and print
    'fundable'. That is precisely the false verdict Â§5 forbids.
    """
    keys = sorted(
        {spec.key for spec in dimensions_for(Scope.FUNDABILITY)},
        key=lambda k: k.value,
    )
    scores = [_score(keys[0], 95)] + [
        _score(key, 0, sufficiency=DataSufficiency.INSUFFICIENT_DATA)
        for key in keys[1:]
    ]

    verdict = synthesise(rubric_version="v1", scores=scores).fundability

    assert verdict.level is not VerdictLevel.READY
    assert verdict.level is VerdictLevel.INSUFFICIENT_DATA


def test_partial_evidence_is_labelled_provisional_not_ready() -> None:
    scores = _all(90)
    scores[0] = _score(
        scores[0].dimension, 0, sufficiency=DataSufficiency.INSUFFICIENT_DATA
    )

    verdict = synthesise(rubric_version="v1", scores=scores).fundability

    assert verdict.level is VerdictLevel.PROVISIONAL
    assert verdict.sufficiency is DataSufficiency.PROVISIONAL
    assert "provisional" in verdict.rationale.lower()


def test_a_provisional_dimension_makes_the_whole_verdict_provisional() -> None:
    """One shaky dimension is enough. Confidence does not average out."""
    scores = _all(90)
    scores[0] = _score(scores[0].dimension, 90, sufficiency=DataSufficiency.PROVISIONAL)

    assert synthesise(rubric_version="v1", scores=scores).fundability.level is (
        VerdictLevel.PROVISIONAL
    )


def test_contradictory_figures_block_the_verdict_entirely() -> None:
    """Scoring data we already believe is wrong would be scoring noise."""
    report = synthesise(
        rubric_version="v1", scores=_all(95), data_integrity_score=Decimal(20)
    )

    assert report.fundability.level is VerdictLevel.INSUFFICIENT_DATA
    assert report.fundability.score is None
    assert "do not agree with each other" in report.fundability.rationale


# ---------------------------------------------------------------------------
# Well-evidenced verdicts
# ---------------------------------------------------------------------------


def test_full_evidence_above_the_bar_reads_ready() -> None:
    report = synthesise(rubric_version="v1", scores=_all(READY_THRESHOLD + 10))

    assert report.fundability.level is VerdictLevel.READY
    assert report.fundability.sufficiency is DataSufficiency.SUFFICIENT
    assert report.fundability.score == READY_THRESHOLD + 10


def test_full_evidence_below_the_bar_reads_not_yet() -> None:
    """Distinct from insufficient_data: this one *was* assessed."""
    report = synthesise(rubric_version="v1", scores=_all(READY_THRESHOLD - 20))

    assert report.fundability.level is VerdictLevel.NOT_YET
    assert report.fundability.sufficiency is DataSufficiency.SUFFICIENT
    assert report.fundability.score is not None


def test_not_yet_tells_the_founder_what_would_change_it() -> None:
    report = synthesise(rubric_version="v1", scores=_all(40))

    assert "action plan" in report.fundability.rationale.lower()


def test_the_two_verdicts_score_different_dimensions() -> None:
    """Saleability asks what happens when the founder leaves; fundability does not."""
    report = synthesise(rubric_version="v1", scores=_all(80))

    fundability = set(report.fundability.evidenced_dimensions)
    saleability = set(report.saleability.evidenced_dimensions)

    assert Dimension.SCALABILITY in fundability
    assert Dimension.SCALABILITY not in saleability
    assert Dimension.OWNER_INDEPENDENCE in saleability
    assert Dimension.OWNER_INDEPENDENCE not in fundability


# ---------------------------------------------------------------------------
# The action plan
# ---------------------------------------------------------------------------


def test_unmet_criteria_become_the_action_plan() -> None:
    scores = _all(80)
    scores[0] = _score(scores[0].dimension, 80, unmet=("Publish audited accounts",))

    plan = synthesise(rubric_version="v1", scores=scores).action_plan

    assert [item.action for item in plan] == ["Publish audited accounts"]


def test_the_worst_scoring_dimension_comes_first() -> None:
    """A founder with limited time should start where it hurts most."""
    scores = _all(90)
    scores[0] = _score(scores[0].dimension, 90, unmet=("high scorer task",))
    scores[1] = _score(scores[1].dimension, 20, unmet=("low scorer task",))

    plan = synthesise(rubric_version="v1", scores=scores).action_plan

    assert [item.action for item in plan] == ["low scorer task", "high scorer task"]


def test_unassessable_dimensions_come_before_merely_low_ones() -> None:
    """'We could not assess this' is cheaper to fix and blocks the verdict itself."""
    scores = _all(90)
    scores[0] = _score(scores[0].dimension, 10, unmet=("fix the low score",))
    scores[1] = _score(
        scores[1].dimension,
        0,
        sufficiency=DataSufficiency.INSUFFICIENT_DATA,
        unmet=("supply the missing evidence",),
    )

    plan = synthesise(rubric_version="v1", scores=scores).action_plan

    assert plan[0].action == "supply the missing evidence"
    assert plan[0].dimension_score is None


# ---------------------------------------------------------------------------
# Reproducibility (T2.9)
# ---------------------------------------------------------------------------


def test_the_same_scores_always_produce_the_same_verdict() -> None:
    """Why the verdict is a rule and not a second opinion from a model."""
    scores = _all(72)

    levels = {
        synthesise(rubric_version="v1", scores=scores).fundability.level
        for _ in range(10)
    }

    assert len(levels) == 1


def test_findings_and_rubric_version_are_carried_through() -> None:
    """An AuditRun must be explainable later, so provenance rides along (D12)."""
    finding = Finding(
        code=FindingCode.REVENUE_VS_ANNUAL,
        severity=Severity.LIKELY,
        fields=("monthly_revenue_minor",),
        message="Please check both figures.",
        detail="10x",
    )

    report = synthesise(rubric_version="v1", scores=_all(80), findings=[finding])

    assert report.rubric_version == "v1"
    assert report.findings == (finding,)


@pytest.mark.parametrize("integrity", [Decimal(0), Decimal(49)])
def test_the_integrity_floor_is_applied_consistently_to_both_verdicts(
    integrity: Decimal,
) -> None:
    report = synthesise(
        rubric_version="v1", scores=_all(95), data_integrity_score=integrity
    )

    assert report.fundability.level is VerdictLevel.INSUFFICIENT_DATA
    assert report.saleability.level is VerdictLevel.INSUFFICIENT_DATA


# ---------------------------------------------------------------------------
# The rubric's declared weights are actually applied
# ---------------------------------------------------------------------------
#
# `DimensionSpec.weight` was defined eleven times and read nowhere: synthesis
# took a plain mean while the field's own docstring claimed "Synthesis (T2.7)
# applies these". Every test above scores every dimension identically, which is
# exactly the shape that cannot see the difference -- so the suite stayed green
# through it. These vary the scores per dimension, which is the only way the
# weighting is observable at all.


def _mixed(core: int, saleability_only: int) -> list[DimensionScore]:
    """Every dimension, with the saleability-only ones scored separately."""
    fundability = {spec.key for spec in dimensions_for(Scope.FUNDABILITY)}
    return [
        _score(spec.key, core if spec.key in fundability else saleability_only)
        for spec in dimensions_for(Scope.SALEABILITY)
    ] + [
        _score(spec.key, core)
        for spec in dimensions_for(Scope.FUNDABILITY)
        if spec.key not in {s.key for s in dimensions_for(Scope.SALEABILITY)}
    ]


def test_a_heavier_dimension_pulls_the_score_further_than_a_lighter_one() -> None:
    """The saleability-only three carry 50 of 150 by weight, 3 of 10 by count.

    Exact rather than banded: a band here would be satisfied by the unweighted
    mean this replaced, which is the whole thing under test. 66 is
    (90*100 + 20*50) / 150; the plain mean would be 69.
    """
    report = synthesise(
        rubric_version="v1", scores=_mixed(core=90, saleability_only=20)
    )

    assert report.saleability.score == 66, "weighted, not the plain mean of 69"


def test_weighting_widens_the_gap_between_the_two_verdicts() -> None:
    """Which is the point: an unweighted mean made the verdicts agree too much.

    `founder-dependent-agency` in the golden set exists to prove a business can
    be plainly less saleable than fundable. Under the plain mean that gap was
    about half what the rubric declares.
    """
    report = synthesise(
        rubric_version="v1", scores=_mixed(core=90, saleability_only=20)
    )

    assert report.fundability.score == 90
    assert report.saleability.score == 66
    assert report.fundability.score - report.saleability.score == 24


def test_the_score_is_normalised_over_what_was_evidenced_not_the_whole_scope() -> None:
    """An unevidenced dimension must not also be charged as a zero.

    It is already counted against the founder twice -- by the coverage gate and
    by the `thin` rule that forces `provisional`. Dividing by the scope's full
    weight would charge it a third time, as a silent score penalty nobody
    declared.
    """
    scores = _all(80)
    scores = [
        _score(s.dimension, 0, sufficiency=DataSufficiency.INSUFFICIENT_DATA)
        if s.dimension is Dimension.LEGAL_AND_IP
        else s
        for s in scores
    ]

    report = synthesise(rubric_version="v1", scores=scores)

    assert report.fundability.score == 80, "the evidenced dimensions all scored 80"


# ---------------------------------------------------------------------------
# The short list a founder is actually shown
# ---------------------------------------------------------------------------
#
# The first live run produced 44 action items. They were specific and correct,
# and a plan that long is functionally the same as no plan. Marked rather than
# truncated: nothing is dropped, and the field is additive for the client.


def _with_actions(**per_dimension: tuple[str, ...]) -> list[DimensionScore]:
    """Every dimension at 80, with unmet criteria on the named ones."""
    return [
        _score(spec.key, 80, unmet=per_dimension.get(spec.key.value, ()))
        for spec in dimensions_for(Scope.SALEABILITY)
    ]


def test_nothing_is_dropped_from_the_plan() -> None:
    """Truncating server-side would lose work the founder still has to do."""
    report = synthesise(
        rubric_version="v1",
        scores=_with_actions(
            legal_and_ip=tuple(f"legal action {n}" for n in range(10)),
            team=("hire a second engineer",),
        ),
    )

    assert len(report.action_plan) == 11


def test_the_short_list_spans_dimensions_rather_than_repeating_one() -> None:
    """ "Top N items" would be N restatements of a single weakness.

    A dimension can raise many unmet criteria, so the short list takes one item
    from each of the worst few dimensions instead.
    """
    report = synthesise(
        rubric_version="v1",
        scores=_with_actions(
            legal_and_ip=tuple(f"legal action {n}" for n in range(10)),
            team=("hire a second engineer",),
            traction=("publish a retention cohort",),
        ),
    )

    priority = [item for item in report.action_plan if item.is_priority]

    assert len(priority) == 3, "one per dimension that has anything to do"
    assert len({item.dimension for item in priority}) == 3


def test_the_short_list_is_capped_even_when_every_dimension_has_work() -> None:
    report = synthesise(
        rubric_version="v1",
        scores=_with_actions(
            **{spec.key.value: ("do the thing",) for spec in dimensions_for(Scope.BOTH)}
        ),
    )

    priority = [item for item in report.action_plan if item.is_priority]

    assert len(priority) == PRIORITY_DIMENSIONS


def test_an_unassessable_dimension_reaches_the_short_list_first() -> None:
    """ "We could not assess this" is cheaper to fix and blocks the verdict."""
    scores = [
        _score(spec.key, 80, unmet=("improve this",))
        for spec in dimensions_for(Scope.SALEABILITY)
    ]
    scores[0] = _score(
        scores[0].dimension,
        0,
        sufficiency=DataSufficiency.INSUFFICIENT_DATA,
        unmet=("tell us about this at all",),
    )

    report = synthesise(rubric_version="v1", scores=scores)

    assert report.action_plan[0].is_priority
    assert report.action_plan[0].dimension is scores[0].dimension
