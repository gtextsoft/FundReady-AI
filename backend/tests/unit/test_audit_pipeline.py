"""T2.8: the stages wired together.

No database and no network -- the AI client takes an injected fake, the same way
`test_rubric_v1.py` drives it, and benchmark lookup is split out of the pipeline
precisely so this file needs no session.

Three things are defended here, and the first two are about spend rather than
correctness -- which is the point: an audit is the most expensive call the
platform makes (D16), so a call that could not change the answer is a real
charge to a real founder.

* **A call that cannot change the answer is not made.** Below the integrity
  floor the verdict is already `insufficient_data`; without documents there is
  no second source to contradict.
* **A figure is never shown in a currency nobody stated.** The absolute money
  figures are the only ones that depend on it, and printing naira as dollars
  into the scoring prompt is the unit-scale falsehood T2.2a and T2.5 exist for.
* **The same profile renders identically however it was assembled** -- T2.9
  compares audits of the same input, and the rendered prompt is part of that
  input.
"""

import json
from dataclasses import fields
from datetime import date
from decimal import Decimal
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AiClient
from app.ai.guards import fence
from app.core.config import Settings
from app.modules.audit import pipeline
from app.modules.audit.benchmarks import BenchmarkMetric, MatchQuality
from app.modules.audit.consistency import FindingCode
from app.modules.audit.finance import Metric, compute
from app.modules.audit.models import Benchmark
from app.modules.audit.rubric import v1
from app.modules.audit.schemas import report_to_storage
from app.modules.audit.service import BenchmarkMatch
from app.modules.audit.synthesis import VerdictLevel, synthesise
from app.modules.intake.fields import FieldSource, Stage
from tests.unit.test_ai_client import _FakeAnthropic, _Message  # noqa: PLC2701


def _client(responses: list[Any]) -> tuple[AiClient, Any]:
    fake = _FakeAnthropic(responses)
    return AiClient(Settings(), client=fake), fake


def _founder(value: Any) -> dict[str, Any]:
    """A field in the shape the profile actually stores."""
    return {"value": value, "source": FieldSource.FOUNDER.value, "confidence": 1.0}


def _healthy_fields() -> dict[str, Any]:
    """A profile whose figures agree with each other -- no findings, integrity 100.

    Deliberately consistent: 12 x monthly revenue is the trailing year, customers
    x ARPU is the monthly revenue, and 2% churn of 100 customers is two people.
    Every one of those is a check in `check_scale`, so a fixture that tripped one
    would make the spend assertions below pass for the wrong reason.
    """
    return {
        "monthly_revenue_minor": _founder(5_000_000),
        "last_12m_revenue_minor": _founder(60_000_000),
        "monthly_costs_minor": _founder(4_000_000),
        "cash_on_hand_minor": _founder(20_000_000),
        "cost_of_revenue_minor": _founder(1_500_000),
        "active_customers": _founder(100),
        "average_revenue_per_customer_minor": _founder(50_000),
        "customer_acquisition_cost_minor": _founder(100_000),
        "monthly_churn_percent": _founder(2.0),
        "team_size": _founder(10),
        "founder_count": _founder(2),
        "founders_full_time": _founder(2),
        "description": _founder("Last-mile delivery for Lagos pharmacies."),
        "business_model": _founder("Per-delivery fee plus a monthly subscription."),
    }


def _snapshot(**overrides: Any) -> pipeline.ProfileSnapshot:
    defaults: dict[str, Any] = {
        "fields": _healthy_fields(),
        "name": "Kite Logistics",
        "sector": "logistics",
        "stage": Stage.SEED,
        "country": "NG",
        "currency": "NGN",
    }
    defaults.update(overrides)
    return pipeline.ProfileSnapshot(**defaults)


def _assessment(rubric_version: str = "v1") -> str:
    return json.dumps(
        {
            "rubric_version": rubric_version,
            "scores": [
                {
                    "dimension": "financial_health",
                    "score": 74,
                    "rationale": "Runway is comfortable on the computed figures.",
                    "unmet_criteria": ["Provide six months of bank statements."],
                    "benchmark_used": None,
                    "sufficiency": "sufficient",
                    "citations": [
                        {
                            "source_id": pipeline.PROFILE_SOURCE_ID,
                            "quote": "monthly_revenue_minor: 5000000",
                        }
                    ],
                }
            ],
        }
    )


def _contradictions(*summaries: str) -> str:
    return json.dumps(
        {
            "contradictions": [
                {
                    "summary": summary,
                    "claim": {"source_id": "deck.pdf", "quote": "34 customers"},
                    "conflicting_claim": {
                        "source_id": "financials.xlsx",
                        "quote": "12 paying accounts",
                    },
                }
                for summary in summaries
            ]
        }
    )


# ---------------------------------------------------------------------------
# Spend: a call that cannot change the answer is not made
# ---------------------------------------------------------------------------


async def test_scoring_is_skipped_when_the_data_cannot_be_trusted() -> None:
    """Below the integrity floor the verdict is fixed, so the rubric is not run.

    `synthesise` returns `insufficient_data` on both verdicts regardless of the
    scores at that point. Paying `claude-opus-5` at high effort to produce them
    anyway would be the platform's most expensive call bought for nothing.
    """
    client, fake = _client([])
    fields = _healthy_fields()
    # Two head-count impossibilities (CERTAIN, 25 each) plus a trailing-revenue
    # mismatch (LIKELY, 15): 65 of penalty, so integrity lands at 35.
    fields["team_size"] = _founder(3)
    fields["founder_count"] = _founder(5)
    fields["founders_full_time"] = _founder(6)
    fields["last_12m_revenue_minor"] = _founder(6_000)

    report = await pipeline.run_pipeline(client, snapshot=_snapshot(fields=fields))

    assert fake.messages.calls == [], "no model call may be made below the floor"
    assert report.fundability.level is VerdictLevel.INSUFFICIENT_DATA
    assert report.saleability.level is VerdictLevel.INSUFFICIENT_DATA
    assert report.data_integrity_score < 50
    assert {f.code for f in report.findings} >= {
        FindingCode.MORE_FOUNDERS_THAN_TEAM,
        FindingCode.MORE_FULL_TIME_THAN_FOUNDERS,
    }


def test_a_report_from_the_skipped_path_is_still_storable() -> None:
    """The branch a founder with contradictory data reaches first.

    `synthesise(scores=())` builds both verdicts from nothing, and
    `report_to_storage` reads `.scope.value` and `.level.value` off them. If
    either were absent the failure would land **after** the audit was billed, in
    a worker, with no request to surface it -- so the cheap assertion is here
    rather than only in the success path's end-to-end test.
    """
    report = synthesise(
        rubric_version="v1", scores=(), data_integrity_score=Decimal(10)
    )

    stored = report_to_storage(report)
    json.dumps(stored)  # JSONB holds plain types; a Decimal would raise here

    assert stored["fundability"]["level"] == "insufficient_data"
    assert stored["saleability"]["level"] == "insufficient_data"
    # A string, not a float: a coerced integrity score is no longer the score
    # that was computed.
    assert stored["data_integrity_score"] == "10"


async def test_a_skipped_audit_still_tells_the_founder_it_was_not_a_failure() -> None:
    """The cheap path must not become the harsh one (`CLAUDE.md` section 5)."""
    client, _ = _client([])
    fields = _healthy_fields()
    fields["founder_count"] = _founder(5)
    fields["team_size"] = _founder(3)
    fields["founders_full_time"] = _founder(6)
    fields["last_12m_revenue_minor"] = _founder(6_000)

    report = await pipeline.run_pipeline(client, snapshot=_snapshot(fields=fields))

    rationale = report.fundability.rationale.lower()
    assert "no verdict has been formed" in rationale
    assert "not fundable" not in rationale


async def test_no_documents_means_no_contradiction_call() -> None:
    """Contradiction detection compares sources. One source is nothing to compare."""
    client, fake = _client([_Message(_assessment())])

    await pipeline.run_pipeline(client, snapshot=_snapshot())

    assert len(fake.messages.calls) == 1, "only the rubric call belongs here"


async def test_documents_are_compared_against_the_profile() -> None:
    client, fake = _client(
        [_Message(_contradictions()), _Message(_assessment())],
    )
    documents = [fence("The deck claims 34 customers.", label="deck.pdf")]

    await pipeline.run_pipeline(client, snapshot=_snapshot(), documents=documents)

    assert len(fake.messages.calls) == 2, "contradictions, then scoring"


# ---------------------------------------------------------------------------
# Contradictions
# ---------------------------------------------------------------------------


async def test_a_contradiction_is_reported_but_charged_only_once() -> None:
    """`data_integrity_score` has its own penalty for contradictions.

    Converting them to findings *and* passing them in as findings would deduct
    twice for one problem, which would push honest profiles below the floor.
    """
    client, _ = _client(
        [
            _Message(_contradictions("Your deck and your financials disagree.")),
            _Message(_assessment()),
        ]
    )
    documents = [fence("34 customers", label="deck.pdf")]

    report = await pipeline.run_pipeline(
        client, snapshot=_snapshot(), documents=documents
    )

    assert report.data_integrity_score == 80, "one contradiction, one 20-point penalty"
    contradictions = [f for f in report.findings if f.code is FindingCode.CONTRADICTION]
    assert len(contradictions) == 1
    assert contradictions[0].message == "Your deck and your financials disagree."


async def test_a_contradiction_keeps_no_figures_in_its_log_context() -> None:
    """Section 4: the founder may see their own figures, a shared log may not."""
    client, _ = _client(
        [
            _Message(_contradictions("Your deck and your financials disagree.")),
            _Message(_assessment()),
        ]
    )

    report = await pipeline.run_pipeline(
        client,
        snapshot=_snapshot(),
        documents=[fence("34 customers", label="deck.pdf")],
    )
    finding = next(f for f in report.findings if f.code is FindingCode.CONTRADICTION)

    assert finding.log_context() == {
        "code": "contradiction",
        "severity": "likely",
        "fields": [],
    }


# ---------------------------------------------------------------------------
# The rubric version is ours
# ---------------------------------------------------------------------------


async def test_one_good_dimension_is_not_a_verdict() -> None:
    """The dangerous case, at the boundary where model output enters.

    Synthesis measures coverage against the dimensions it is handed, so an
    assessment returning a single 74 out of eleven dimensions would read as
    fully covered and come back `ready` -- a "fundable" off one data point,
    which `CLAUDE.md` section 5 forbids as a guarantee rather than a preference.
    The unreturned dimensions are padded as unassessed, which is what they are.
    """
    client, _ = _client([_Message(_assessment())])

    report = await pipeline.run_pipeline(client, snapshot=_snapshot())

    assert report.fundability.level is VerdictLevel.INSUFFICIENT_DATA
    assert report.saleability.level is VerdictLevel.INSUFFICIENT_DATA
    assert report.fundability.score is None


async def test_a_dimension_the_model_skipped_is_still_shown_to_the_founder() -> None:
    """It must not vanish: a founder is owed the list of what was not assessed."""
    client, _ = _client([_Message(_assessment())])

    report = await pipeline.run_pipeline(client, snapshot=_snapshot())

    in_scope = {spec.key for spec in v1.dimensions_for(v1.Scope.FUNDABILITY)}
    reported = set(report.fundability.evidenced_dimensions) | set(
        report.fundability.unevidenced_dimensions
    )
    assert reported == in_scope


async def test_the_recorded_rubric_version_is_not_the_models_echo() -> None:
    """D12: a run stays explainable, so its version is the one this code asked for."""
    client, _ = _client([_Message(_assessment(rubric_version="v99"))])

    report = await pipeline.run_pipeline(client, snapshot=_snapshot())

    assert report.rubric_version == v1.RUBRIC_VERSION


# ---------------------------------------------------------------------------
# Reading the profile document
# ---------------------------------------------------------------------------


def test_a_bare_value_is_read_like_a_wrapped_one() -> None:
    """`merge_into_profile` guards with `isinstance`, so both shapes are storable."""
    wrapped = pipeline.financial_inputs(_snapshot())
    bare = pipeline.financial_inputs(
        _snapshot(
            fields={
                name: (spec["value"] if isinstance(spec, dict) else spec)
                for name, spec in _healthy_fields().items()
            }
        )
    )

    assert wrapped == bare


def test_a_value_of_the_wrong_type_is_dropped_rather_than_guessed_at() -> None:
    """A misread figure that reaches the rubric becomes a score (T2.4)."""
    inputs = pipeline.financial_inputs(
        _snapshot(fields={"monthly_revenue_minor": _founder("about 5 million")})
    )

    assert inputs.monthly_revenue_minor is None


def test_a_boolean_is_never_read_as_a_number() -> None:
    """`isinstance(True, int)` is True in Python -- a team of `true` is a team of 1."""
    inputs = pipeline.financial_inputs(
        _snapshot(fields={"monthly_revenue_minor": _founder(True)})
    )

    assert inputs.monthly_revenue_minor is None


# ---------------------------------------------------------------------------
# Rendering: currency, sources, determinism
# ---------------------------------------------------------------------------


def test_money_is_never_printed_in_a_currency_nobody_stated() -> None:
    """The dataclass default is USD; a profile with no currency is not American."""
    summary = compute(pipeline.financial_inputs(_snapshot(currency=None)))

    rendered = pipeline.render_computed_figures(summary)

    assert "USD" not in rendered
    assert "currency: not stated by the founder" in rendered
    assert "net_burn_minor: not shown" in rendered
    # The ratios do not depend on the currency and must still be scored on.
    assert "gross_margin_percent: 70" in rendered


def test_every_computed_figure_reaches_the_prompt() -> None:
    """A figure `finance.py` works out and the prompt never shows is a wasted one.

    The rendering table is written by hand so the order is fixed (T2.9), which
    means a metric added to `FinancialSummary` would be silently dropped here --
    and "not computed" and "computed but not shown" look identical from the
    model's side. Same guard `test_benchmark_vocabulary.py` puts on T2.3.
    """
    summary = compute(pipeline.financial_inputs(_snapshot()))
    computed = {
        f.name for f in fields(summary) if isinstance(getattr(summary, f.name), Metric)
    }

    assert computed == {name for name, _ in pipeline._FIGURE_RENDERING}


def test_a_figure_that_could_not_be_computed_says_why() -> None:
    """Rule 3 of the scoring prompt: absent is not the same as bad."""
    summary = compute(
        pipeline.financial_inputs(_snapshot(fields={"team_size": _founder(4)}))
    )

    rendered = pipeline.render_computed_figures(summary)

    assert "gross_margin_percent: not computable (missing_input)" in rendered


def test_profile_facts_name_a_source_the_model_can_cite() -> None:
    """Without a named source, a model told to cite will invent a filename."""
    rendered = pipeline.render_profile_facts(_snapshot())

    assert f"source_id: {pipeline.PROFILE_SOURCE_ID}" in rendered


def test_every_fact_says_where_it_came_from() -> None:
    """Rule 4 of the scoring prompt: corroboration beats assertion."""
    fields = _healthy_fields()
    fields["monthly_revenue_minor"] = {
        "value": 5_000_000,
        "source": FieldSource.DOCUMENT.value,
        "confidence": 0.9,
    }

    rendered = pipeline.render_profile_facts(_snapshot(fields=fields))

    assert "monthly_revenue_minor: 5000000 [source: document]" in rendered
    assert "team_size: 10 [source: founder]" in rendered


def test_the_same_profile_renders_identically_however_it_was_assembled() -> None:
    """T2.9's same-input-same-score: the rendered prompt is part of the input."""
    fields = _healthy_fields()
    reversed_order = dict(reversed(list(fields.items())))

    assert pipeline.render_profile_facts(
        _snapshot(fields=fields)
    ) == pipeline.render_profile_facts(_snapshot(fields=reversed_order))


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------


def _band(metric: BenchmarkMetric, **overrides: Any) -> Benchmark:
    values: dict[str, Any] = {
        "sector": "logistics",
        "stage": Stage.SEED,
        "metric": metric,
        "region": "NG",
        "p25": 40,
        "p50": 55,
        "p75": 68,
        "source": "SACI panel",
        "as_of_date": date(2026, 1, 1),
    }
    values.update(overrides)
    return Benchmark(**values)


def test_a_weak_band_is_labelled_as_weak() -> None:
    """An all-sectors global median is context, not a peer comparison (T2.3)."""
    summary = compute(pipeline.financial_inputs(_snapshot()))
    matches = {
        BenchmarkMetric.GROSS_MARGIN_PERCENT: BenchmarkMatch(
            benchmark=_band(
                BenchmarkMetric.GROSS_MARGIN_PERCENT, sector="*", region="*"
            ),
            quality=MatchQuality.BROAD,
        )
    }

    rendered = pipeline.render_benchmark_context(matches, summary)

    assert "Match quality: broad" in rendered
    assert "weak evidence" in rendered
    # 70% gross margin against p75 of 68: the top of the band, read in the
    # direction that is good for this metric.
    assert "sits in the top of that band" in rendered


def test_benchmarks_render_in_a_fixed_order() -> None:
    """Insertion order of the lookup must not reach the prompt (T2.9)."""
    summary = compute(pipeline.financial_inputs(_snapshot()))
    forwards = {
        BenchmarkMetric.GROSS_MARGIN_PERCENT: BenchmarkMatch(
            benchmark=_band(BenchmarkMetric.GROSS_MARGIN_PERCENT),
            quality=MatchQuality.EXACT,
        ),
        BenchmarkMetric.RUNWAY_MONTHS: BenchmarkMatch(
            benchmark=_band(BenchmarkMetric.RUNWAY_MONTHS),
            quality=MatchQuality.EXACT,
        ),
    }
    backwards = dict(reversed(list(forwards.items())))

    assert pipeline.render_benchmark_context(
        forwards, summary
    ) == pipeline.render_benchmark_context(backwards, summary)


def test_nothing_matched_renders_as_nothing() -> None:
    """D11: an empty string, never a plausible default the model would trust."""
    summary = compute(pipeline.financial_inputs(_snapshot()))

    assert pipeline.render_benchmark_context({}, summary) == ""


async def test_a_profile_with_no_stage_is_not_compared_to_one() -> None:
    """Stage is matched exactly, so no stage means no peer group -- and no query."""
    summary = compute(pipeline.financial_inputs(_snapshot(stage=None)))

    # The session is deliberately `None`: touching it here would be the bug.
    context = await pipeline.assemble_benchmark_context(
        cast(AsyncSession, None), _snapshot(stage=None), summary
    )

    assert context == ""
