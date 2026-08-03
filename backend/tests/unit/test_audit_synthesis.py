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
# Thin data never produces a confident verdict (CLAUDE.md §5)
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
    'fundable'. That is precisely the false verdict §5 forbids.
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
