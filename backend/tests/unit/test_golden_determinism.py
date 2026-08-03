"""T2.9, half one: same input, same score -- proven where it can be proven.

The audit has a model in the middle of it, so "deterministic" cannot be claimed
for the whole pipeline. It can be claimed, and is claimed here, for everything
on either side of that one call:

* **The rendered prompt**, because it is part of "same input". A profile whose
  `fields` come back from JSONB in a different order must produce a
  byte-identical prompt, or two runs of the same audit were never given the
  same question.
* **The consistency layer**, which is arithmetic over a fixed table.
* **`synthesise`**, which computes the verdict rather than asking for one --
  the reason `synthesis.py` gives for that design is precisely this test.

What is left over -- whether the model's dimension scores are stable, and
whether they agree with a human -- is the billed half, in
`test_golden_accuracy.py`. Keeping the two apart matters: this file runs free
and in CI, and a green run of it says nothing about accuracy.
"""

from decimal import Decimal
from typing import Any

import pytest

from app.ai.schemas import Citation, DataSufficiency
from app.modules.audit.consistency import check_scale, check_team, data_integrity_score
from app.modules.audit.finance import compute
from app.modules.audit.pipeline import (
    ProfileSnapshot,
    financial_inputs,
    render_computed_figures,
    render_profile_facts,
)
from app.modules.audit.rubric.v1 import (
    RUBRIC_VERSION,
    Dimension,
    DimensionScore,
    Scope,
    dimensions_for,
)
from app.modules.audit.synthesis import (
    _MIN_SUFFICIENT_RATIO,
    INTEGRITY_FLOOR,
    READY_THRESHOLD,
    VerdictLevel,
    synthesise,
)
from app.modules.intake.fields import FIELDS_BY_NAME, value_error
from tests.golden import ExpectedVerdict, GoldenCompany, load_companies
from tests.golden.loader import (
    NARRATIVE_FIELDS,
    NARRATIVE_ONLY_DIMENSIONS,
    SUBSTANTIVE_NARRATIVE_CHARS,
    ReviewedBy,
    as_ids,
    qualified_ids,
)

# Ten was already the bar `test_audit_consistency` set for `data_integrity_score`.
# Matched here so "stable" means the same thing across the suite.
RUNS = 10

COMPANIES = load_companies()

SCOPES: tuple[tuple[str, Scope], ...] = (
    ("fundability", Scope.FUNDABILITY),
    ("saleability", Scope.SALEABILITY),
)
"""The two verdicts, paired with the name the failure message should use.

`Scope.BOTH` is deliberately absent: it is the set every dimension belongs to,
not a third verdict, and `_verdict_for` is never called with it.
"""


def _findings(company: GoldenCompany) -> list[Any]:
    """One company's arithmetic findings, exactly as `run_pipeline` builds them."""
    fields = company.snapshot.fields
    inputs = financial_inputs(company.snapshot)
    return [
        *check_scale(inputs, active_customers=_int(fields, "active_customers")),
        *check_team(
            team_size=_int(fields, "team_size"),
            founder_count=_int(fields, "founder_count"),
            founders_full_time=_int(fields, "founders_full_time"),
        ),
    ]


def _int(fields: Any, name: str) -> int | None:
    entry = fields.get(name)
    if not isinstance(entry, dict):
        return None
    value = entry.get("value")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


# ---------------------------------------------------------------------------
# The fixtures themselves
# ---------------------------------------------------------------------------


def test_the_golden_set_loads() -> None:
    """A parse error here would otherwise surface as an empty eval report."""
    assert COMPANIES, "the golden set is empty"
    assert len({company.id for company in COMPANIES}) == len(COMPANIES)


def test_every_company_says_why_it_exists() -> None:
    """A fixture nobody can justify is a fixture nobody will maintain."""
    for company in COMPANIES:
        assert company.why_this_case.strip(), f"{company.id} has no rationale"


@pytest.mark.parametrize("company", COMPANIES, ids=as_ids(COMPANIES))
def test_every_field_would_survive_the_intake_validator(company: GoldenCompany) -> None:
    """A golden profile the API would reject is not a golden profile.

    These fixtures build `ProfileSnapshot` directly -- which is what lets the
    pipeline be exercised with no database, and also what lets an impossible
    value in unnoticed. `key_person_dependency` is TEXT ("what breaks if a
    specific person leaves"), and the first draft of this set put booleans in
    it: five companies that could never have come through `POST /v1/startups`,
    quietly scoring the rubric against data no founder could submit.
    """
    for name, entry in company.snapshot.fields.items():
        spec = FIELDS_BY_NAME.get(name)
        assert spec is not None, f"{company.id}: unknown field {name!r}"

        problem = value_error(spec, entry["value"])
        assert problem is None, f"{company.id}.{name}: {problem}"


def test_expected_scores_match_what_the_level_can_produce() -> None:
    """Both directions, because only checking one of them missed a real bug.

    `_verdict_for` sets `score=None` on `insufficient_data` and `score=mean` on
    every other level -- **including `provisional`**, which is a conclusion drawn
    from partial evidence, not an absence of one. So an expectation pairing
    `insufficient_data` with a band is unsatisfiable, and so is one pairing
    `provisional` (or `ready`, or `not_yet`) with no band at all. The first
    draft of `pre-revenue-deeptech` did exactly the latter and this test only
    checked the former, so it passed.
    """
    for company in COMPANIES:
        for name, expected in (
            ("fundability", company.fundability),
            ("saleability", company.saleability),
        ):
            has_band = expected.score_min is not None or expected.score_max is not None

            if expected.level is VerdictLevel.INSUFFICIENT_DATA:
                assert not has_band, (
                    f"{company.id}.{name}: insufficient_data always scores None, "
                    "so a band here can never match"
                )
            else:
                assert has_band, (
                    f"{company.id}.{name}: {expected.level.value} always carries a "
                    "score, so an expectation of None can never match"
                )


# ---------------------------------------------------------------------------
# Coverage decides the level before any score does
# ---------------------------------------------------------------------------
#
# The rule these tests encode is one line of `_verdict_for`:
#
#     thin = unevidenced or any(sufficiency is PROVISIONAL for evidenced)
#
# `ready` and `not_yet` are both behind `not thin`, so **either level requires
# every single in-scope dimension to come back `sufficient`** -- 8 of 8 for
# fundability, 10 of 10 for saleability. One hedged dimension collapses the
# verdict to `provisional` however strong the rest of the submission is.
#
# That is easy to miss and expensive to discover: it can only fail on a billed
# run, and it fails as "the model disagreed" rather than as "this expectation
# was never reachable". Five of the eight fixtures asserted a level their own
# profile could not produce before these tests existed.


def _forced_level(company: GoldenCompany, scope: Scope) -> VerdictLevel | None:
    """The level this profile's coverage forces, or `None` if scores decide.

    A statement about the fixture, not a prediction about the model: every
    input is `evidence_for`, which reads the profile. `None` means coverage is
    complete and the verdict then turns on the scores, which is the only case
    where `ready` and `not_yet` are distinguishable.
    """
    if data_integrity_score(_findings(company), ()) < INTEGRITY_FLOOR:
        return VerdictLevel.INSUFFICIENT_DATA

    keys = tuple(spec.key for spec in dimensions_for(scope))
    evidenced = sum(1 for key in keys if company.evidence_for(key))
    covered = Decimal(evidenced) / Decimal(len(keys))
    if evidenced == 0 or covered < _MIN_SUFFICIENT_RATIO:
        return VerdictLevel.INSUFFICIENT_DATA
    return VerdictLevel.PROVISIONAL if evidenced < len(keys) else None


def _assert_band_can_produce_the_level(
    company_id: str, name: str, expected: ExpectedVerdict
) -> None:
    """`ready` and `not_yet` are separated by `READY_THRESHOLD`, not by taste.

    Once coverage is complete, `_verdict_for` picks between them on
    `mean >= READY_THRESHOLD` alone -- so a `ready` band starting below the
    threshold, or a `not_yet` band reaching it, describes an outcome the code
    cannot produce. The expectation would then fail on a **billed** run and
    read as "the model disagreed" rather than as "this was never satisfiable",
    which is the whole failure mode this file exists to move earlier.

    Only these two levels are constrained. `provisional` carries a mean as well
    but is chosen before the threshold is ever consulted, so its band is free.
    """
    low, high = expected.score_min, expected.score_max
    if expected.level is VerdictLevel.READY:
        assert low is not None and low >= READY_THRESHOLD, (
            f"{company_id}.{name}: ready needs a mean of at least "
            f"{READY_THRESHOLD}, so a band starting at {low} is unsatisfiable"
        )
    elif expected.level is VerdictLevel.NOT_YET:
        assert high is not None and high < READY_THRESHOLD, (
            f"{company_id}.{name}: not_yet needs a mean below "
            f"{READY_THRESHOLD}, so a band reaching {high} is unsatisfiable -- "
            "any run landing there would have been ready"
        )


@pytest.mark.parametrize("company", COMPANIES, ids=as_ids(COMPANIES))
def test_the_expected_level_is_one_the_profile_can_reach(
    company: GoldenCompany,
) -> None:
    """No fixture may assert a level its own coverage rules out."""
    for (name, scope), expected in zip(
        SCOPES, (company.fundability, company.saleability), strict=True
    ):
        forced = _forced_level(company, scope)
        keys = tuple(spec.key for spec in dimensions_for(scope))
        bare = [key.value for key in keys if not company.evidence_for(key)]

        if forced is None:
            assert expected.level in (VerdictLevel.READY, VerdictLevel.NOT_YET), (
                f"{company.id}.{name}: every dimension is evidenced, so the "
                f"score decides -- {expected.level.value} is not a score outcome"
            )
            _assert_band_can_produce_the_level(company.id, name, expected)
        else:
            assert expected.level is forced, (
                f"{company.id}.{name}: expects {expected.level.value} but "
                f"coverage forces {forced.value}. Nothing citable for: "
                f"{', '.join(bare) or 'nothing'}"
            )


@pytest.mark.parametrize("company", COMPANIES, ids=as_ids(COMPANIES))
def test_no_fixture_sits_on_the_coverage_boundary(company: GoldenCompany) -> None:
    """`covered < 0.5` is strict, so exactly half is a one-dimension coin flip.

    A fixture landing on the line still passes today and swings between
    `provisional` and `insufficient_data` the moment anyone adds or removes a
    single field. That is a fixture defect whether or not it is currently
    green, so it is caught here rather than in a billed run.
    """
    for name, scope in SCOPES:
        keys = tuple(spec.key for spec in dimensions_for(scope))
        evidenced = sum(1 for key in keys if company.evidence_for(key))

        assert Decimal(evidenced) / Decimal(len(keys)) != _MIN_SUFFICIENT_RATIO, (
            f"{company.id}.{name}: coverage is exactly {evidenced}/{len(keys)}, "
            "the boundary itself. Add or remove evidence so the expectation "
            "does not hinge on one dimension"
        )


@pytest.mark.parametrize("company", COMPANIES, ids=as_ids(COMPANIES))
def test_narrative_evidence_is_not_a_borderline_call(company: GoldenCompany) -> None:
    """The length proxy must be deciding easy cases, not close ones.

    `SUBSTANTIVE_NARRATIVE_CHARS` cannot tell a market derivation from padding.
    It is defensible only while every fixture is far from it -- so this asserts
    the margin rather than the threshold, and a fixture that lands near the
    line is told to get a human reading instead of a tuned constant.
    """
    margin = 100
    for dimension in NARRATIVE_ONLY_DIMENSIONS:
        length = company.narrative_length(dimension)
        assert abs(length - SUBSTANTIVE_NARRATIVE_CHARS) > margin, (
            f"{company.id}: {NARRATIVE_FIELDS[dimension]} is {length} characters, "
            f"within {margin} of the {SUBSTANTIVE_NARRATIVE_CHARS}-character "
            f"threshold that decides whether {dimension.value} counts as "
            "evidenced. Too close for a length proxy to be honest about"
        )


def test_a_divergence_claim_is_carried_by_more_than_two_overlapping_bands() -> None:
    """The fixture that proves the verdicts can diverge has to actually prove it.

    `founder-dependent-agency` exists because a profitable business that dies
    without its founder should score worse on saleability than on fundability.
    Bands cannot express that on their own: 46-69 and 32-58 are **both**
    satisfied by a run that returned 50 and 50, which is exactly the outcome
    the fixture is meant to fail on -- the saleability dimensions doing no work.

    So the bands are required not to overlap, which makes the ordering true of
    every satisfying run rather than merely likely. `saleability_below_fundability`
    then tells the accuracy half to compare the two observed scores directly,
    and this test guarantees that instruction is not contradicted by the very
    bands it sits next to.
    """
    claimed = [c for c in COMPANIES if c.saleability_below_fundability]
    assert claimed, "no fixture claims divergence -- the two verdicts are untested"

    for company in claimed:
        low = company.fundability.score_min
        high = company.saleability.score_max
        assert low is not None and high is not None, (
            f"{company.id}: claims divergence but one verdict carries no band"
        )
        assert high < low, (
            f"{company.id}: saleability tops out at {high} and fundability "
            f"starts at {low}, so a run scoring both the same passes both "
            "bands while demonstrating no divergence at all"
        )


def test_reviewed_by_deterministic_means_no_model_is_involved() -> None:
    """The two provenance claims have to agree, or one of them is decoration.

    `deterministic` says no judgement of anyone's is in the expectation.
    `verdict_is_model_dependent` says the verdict needs a model call. A company
    claiming the first while admitting the second is claiming zero circularity
    for a number a model produced.
    """
    for company in COMPANIES:
        if company.reviewed_by is ReviewedBy.DETERMINISTIC:
            assert not company.verdict_is_model_dependent, (
                f"{company.id}: scored 'deterministic' but its verdict depends "
                "on a model call, so it is not free of judgement"
            )


def test_every_expectation_records_whose_judgement_it_is() -> None:
    """An unreviewed fixture cannot carry a provenance, and vice versa."""
    for company in COMPANIES:
        assert company.reviewed, (
            f"{company.id}: unreviewed. The accuracy half skips it silently, so "
            "an eval report would print a pass over a company nobody scored"
        )


def test_integrity_expectations_are_exact_not_banded() -> None:
    """`data_integrity_score` is arithmetic, so a band is slack hiding a bug.

    The first draft banded these 0-49 and 50-90, which let `unit-error-kobo`
    sit at any of fifty values and still pass -- including values only two of
    its three findings could produce.
    """
    for company in COMPANIES:
        assert company.data_integrity_min == company.data_integrity_max, (
            f"{company.id}: integrity is derivable exactly "
            f"({company.data_integrity_min}..{company.data_integrity_max}). "
            "Compute it and assert the figure"
        )


# ---------------------------------------------------------------------------
# The rendered prompt is part of "same input"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("company", COMPANIES, ids=as_ids(COMPANIES))
def test_profile_rendering_is_stable(company: GoldenCompany) -> None:
    renders = {render_profile_facts(company.snapshot) for _ in range(RUNS)}

    assert len(renders) == 1, f"{company.id} rendered differently across runs"


@pytest.mark.parametrize("company", COMPANIES, ids=as_ids(COMPANIES))
def test_profile_rendering_ignores_field_order(company: GoldenCompany) -> None:
    """The real risk, and the one a repeated-call test cannot catch.

    `fields` is JSONB. Postgres does not promise key order, so two reads of the
    same row can hand the pipeline dicts that differ only in insertion order.
    `render_profile_facts` follows `PROFILE_FIELDS` declaration order for
    exactly this reason; without that, the same profile would produce two
    different prompts and T2.9's guarantee would be lost before the model was
    ever reached.
    """
    reversed_fields = dict(reversed(list(company.snapshot.fields.items())))
    shuffled = ProfileSnapshot(
        fields=reversed_fields,
        name=company.snapshot.name,
        sector=company.snapshot.sector,
        stage=company.snapshot.stage,
        country=company.snapshot.country,
        currency=company.snapshot.currency,
    )

    assert render_profile_facts(shuffled) == render_profile_facts(company.snapshot)


@pytest.mark.parametrize("company", COMPANIES, ids=as_ids(COMPANIES))
def test_computed_figures_render_stably(company: GoldenCompany) -> None:
    summary = compute(financial_inputs(company.snapshot))
    renders = {render_computed_figures(summary) for _ in range(RUNS)}

    assert len(renders) == 1


# ---------------------------------------------------------------------------
# The consistency layer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("company", COMPANIES, ids=as_ids(COMPANIES))
def test_data_integrity_is_stable(company: GoldenCompany) -> None:
    scores = {data_integrity_score(_findings(company)) for _ in range(RUNS)}

    assert len(scores) == 1, f"{company.id} scored integrity differently across runs"


@pytest.mark.parametrize("company", COMPANIES, ids=as_ids(COMPANIES))
def test_data_integrity_lands_in_its_expected_band(company: GoldenCompany) -> None:
    """Free to check: no model is involved in this number by design."""
    score = data_integrity_score(_findings(company))

    assert company.integrity_accepts(score), (
        f"{company.id} scored {score}, expected "
        f"{company.data_integrity_min}-{company.data_integrity_max}"
    )


@pytest.mark.parametrize("company", COMPANIES, ids=as_ids(COMPANIES))
def test_expected_findings_actually_fire(company: GoldenCompany) -> None:
    """Both a check of the checker and a check of the fixture.

    A `must_flag` naming a code the arithmetic cannot produce for that profile
    is a broken expectation, and it would otherwise sit in the file looking
    like coverage.
    """
    fired = {finding.code for finding in _findings(company)}

    for code in company.must_flag:
        assert code in fired, f"{company.id} did not flag {code.value}"


# ---------------------------------------------------------------------------
# The verdict, where arithmetic alone decides it
# ---------------------------------------------------------------------------


def test_a_contradicted_profile_is_refused_without_calling_the_model() -> None:
    """The one verdict the deterministic layer can assert end to end.

    Below `INTEGRITY_FLOOR`, `synthesise` returns `insufficient_data` on both
    scopes *whatever the scores are* -- which is why `run_pipeline` skips the
    rubric call entirely. Passing deliberately absurd scores proves the floor
    dominates them rather than merely coinciding with them.
    """
    company = next(c for c in COMPANIES if c.id == "unit-error-kobo")
    integrity = data_integrity_score(_findings(company))

    assert integrity < INTEGRITY_FLOOR, (
        "this fixture exists to fall below the floor; it no longer does"
    )

    report = synthesise(
        rubric_version=RUBRIC_VERSION,
        scores=[
            DimensionScore(
                dimension=dimension,
                score=100,
                rationale="Deliberately perfect, to prove the floor wins.",
                sufficiency=DataSufficiency.SUFFICIENT,
                citations=[Citation(source_id="startup_profile", quote="revenue")],
            )
            for dimension in Dimension
        ],
        data_integrity_score=integrity,
        findings=_findings(company),
    )

    assert report.fundability.level is VerdictLevel.INSUFFICIENT_DATA
    assert report.saleability.level is VerdictLevel.INSUFFICIENT_DATA
    assert report.fundability.score is None
    assert report.saleability.score is None


def test_synthesis_is_stable() -> None:
    """The verdict is arithmetic, so ten runs must agree exactly."""
    scores = [
        DimensionScore(
            dimension=dimension,
            score=72,
            rationale="Stable input for a determinism check.",
            unmet_criteria=["Publish audited accounts."],
            sufficiency=DataSufficiency.SUFFICIENT,
            citations=[
                Citation(source_id="startup_profile", quote="revenue 450000000")
            ],
        )
        for dimension in Dimension
    ]

    reports = [
        synthesise(
            rubric_version=RUBRIC_VERSION,
            scores=scores,
            data_integrity_score=Decimal(95),
        )
        for _ in range(RUNS)
    ]

    first = reports[0]
    for report in reports[1:]:
        assert report == first


# ---------------------------------------------------------------------------
# What is not proven here
# ---------------------------------------------------------------------------


def test_accuracy_is_not_claimed_by_this_file() -> None:
    """Guards the honesty of the harness, not the behaviour of the code.

    The set is reviewed now, so the old form of this test -- "nobody has scored
    anything yet" -- has nothing left to say. The dishonesty it was guarding
    against did not go away with it; it moved. Every model-dependent
    expectation here was scored by Claude against the published rubric, so an
    eval report that prints a bare agreement percentage is reporting that the
    same model family agreed with itself and calling it accuracy.

    This asserts the caveat is still *required*: the moment an analyst reviews
    the set, `ReviewedBy.HUMAN` appears and this test starts telling whoever
    reads it that the qualification can be dropped for those companies.
    """
    grouped = qualified_ids()

    assert not grouped[ReviewedBy.HUMAN], (
        "a human has scored part of the set -- the eval report may now present "
        f"these as plain accuracy: {grouped[ReviewedBy.HUMAN]}"
    )
    assert grouped[ReviewedBy.ASSISTANT_DRAFT], (
        "no assistant-drafted expectations left, but no human ones either -- "
        "one of the two provenance claims is wrong"
    )
