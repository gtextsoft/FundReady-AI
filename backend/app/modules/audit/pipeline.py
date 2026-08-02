"""Audit stage orchestration.

Runs on the background worker, never inline in a request (DECISIONS.md D14).
`audit.service` enqueues the job; `app.workers.tasks` invokes this pipeline.

Stages (ARCHITECTURE.md section 4):
  1. extraction        -- documents to Startup Profile fields, with source and
                          confidence per field, plus missing-field flags
  2. consistency check -- cross-document contradictions to a dataIntegrityScore
  3. finance           -- `finance.py`, in code, no LLM (DECISIONS.md D9)
  4. rubric scoring    -- versioned rubric via `app.ai`, structured output only
  5. synthesis         -- verdicts, founder report, action plan
  6. persistence       -- AuditRun (with rubricVersion) plus embeddings

The whole pipeline must be idempotent and safe to retry.

**`run_pipeline` takes no session and no ORM object.** That is the seam that
makes it testable, and it is not a stylistic preference: CI has no
`DATABASE_URL`, so every `requires_database` test skips there (TASKS.md) -- a
session-bound pipeline would be a pipeline nobody runs on a push. The one part
that genuinely needs the database, benchmark lookup, is split out into
`assemble_benchmark_context`, which hands `run_pipeline` a plain string. Same
seam the rest of the module already uses: `extraction.extract_fields` takes
bytes rather than a storage key, and `rubric.v1.score` takes rendered text
rather than `Benchmark` rows.

**Stage 1 is not wired here yet (T2.4a).** R2 is unprovisioned, so no document
has ever been fetched. `documents` is a parameter rather than something this
module goes and gets, so wiring storage in is an argument at the call site, not
a rewrite of the orchestration.

**This module never computes the idempotency fingerprint.** `runs.input_fingerprint`
requires the *persisted* JSONB -- a `Decimal("42.5000")` written to Postgres
reads back as `42.5`, and the two hash differently. The pipeline works from an
in-memory snapshot, so hashing here would silently bill a founder twice for one
audit. The service creates the AuditRun and owns the hash; the pipeline is
handed work that has already been deduplicated.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AiClient
from app.ai.guards import UntrustedContent
from app.ai.schemas import DataSufficiency
from app.modules.audit import service as audit_service
from app.modules.audit.benchmarks import (
    ANY_SECTOR,
    GLOBAL_REGION,
    BenchmarkMetric,
    MatchQuality,
    higher_is_better,
    quartile_position,
)
from app.modules.audit.consistency import (
    Contradiction,
    Finding,
    FindingCode,
    Severity,
    check_scale,
    check_team,
    data_integrity_score,
    find_contradictions,
)
from app.modules.audit.finance import (
    FinancialInputs,
    FinancialSummary,
    Metric,
    compute,
    to_major_units,
)
from app.modules.audit.rubric import v1
from app.modules.audit.synthesis import INTEGRITY_FLOOR, AuditReport, synthesise
from app.modules.intake.fields import PROFILE_FIELDS, FieldKind, Stage

logger = logging.getLogger(__name__)

__all__ = [
    "PROFILE_SOURCE_ID",
    "UNKNOWN_CURRENCY",
    "ProfileSnapshot",
    "assemble_benchmark_context",
    "financial_inputs",
    "render_benchmark_context",
    "render_computed_figures",
    "render_profile_facts",
    "run_pipeline",
]


PROFILE_SOURCE_ID: Final = "startup_profile"
"""What the model cites when the evidence is the profile itself.

Every score has to cite its source (`CLAUDE.md` section 5). With no documents
uploaded the only evidence is what the founder typed, and a model asked to cite
something unnamed will name a plausible file that does not exist. Naming the
block gives an honest citation a target.
"""

_SCOPE: Final = v1.Scope.BOTH
"""Both verdicts, one pass.

The PRD asks whether a business is fundable *and* saleable, and the two share
most of their dimensions -- so they are scored together rather than paying for
two passes over the same evidence. Named rather than left as `score`'s default
because `_with_unanswered_dimensions` has to pad against the same set that was
asked for; the two drifting apart would pad dimensions nobody requested.
"""

UNKNOWN_CURRENCY: Final = "XXX"
"""ISO 4217's own code for "no currency".

`FinancialInputs.currency` defaults to `USD`, which is the right default for a
dataclass and the wrong one for a profile that has not stated a currency:
rendering a naira burn into the scoring prompt as dollars is precisely the
unit-scale falsehood T2.2a and T2.5 exist to catch. Carrying `XXX` instead lets
the renderer say the currency is unknown and withhold the absolute figures,
which are the only ones that depend on it -- every ratio is dimensionless.
"""


@dataclass(frozen=True, slots=True)
class ProfileSnapshot:
    """A Startup Profile as the pipeline sees it: plain data, no ORM, no session.

    The five indexed columns plus the JSONB document, exactly as
    `intake.models.StartupProfile` stores them. Built by the caller, which is
    what keeps `audit` from importing another module's models
    (`ARCHITECTURE.md` section 3) and keeps the pipeline runnable in CI.

    Everything is optional because a half-known profile is the normal case
    (`intake/fields.py`), not an error.
    """

    fields: Mapping[str, Any] = field(default_factory=dict)
    """The `fields` JSONB: `{name: {"value": ..., "source": ..., ...}}`."""

    name: str | None = None
    sector: str | None = None
    stage: Stage | None = None
    country: str | None = None
    currency: str | None = None


# ---------------------------------------------------------------------------
# Reading the profile document
# ---------------------------------------------------------------------------


def _value(fields: Mapping[str, Any], name: str) -> Any:
    """One field's value, whether or not it is wrapped.

    The stored shape is `{"value": ..., "source": ..., "confidence": ...}`, but
    `extraction.merge_into_profile` guards its own read with an `isinstance`
    check rather than assuming the envelope -- so a bare scalar is a shape this
    profile can genuinely hold, and reading `.get("value")` blindly would raise
    on it.
    """
    raw = fields.get(name)
    if isinstance(raw, dict):
        return raw.get("value")
    return raw


def _source(fields: Mapping[str, Any], name: str) -> str | None:
    """Where the value came from, or `None` when it was stored unwrapped."""
    raw = fields.get(name)
    if isinstance(raw, dict):
        source = raw.get("source")
        return str(source) if source is not None else None
    return None


def _int(fields: Mapping[str, Any], name: str) -> int | None:
    value = _value(fields, name)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def financial_inputs(snapshot: ProfileSnapshot) -> FinancialInputs:
    """The raw figures `finance.compute` needs, lifted out of the profile.

    Name-for-name: every field here is a `FieldSpec` in `intake/fields.py` and a
    field on `FinancialInputs`. Anything of the wrong type is dropped rather
    than coerced -- `value_error` already refused it at the boundary, so a bad
    type here means the JSONB was written by something that bypassed it, and
    guessing at what it meant is how a misread figure becomes a score.
    """
    churn = _value(snapshot.fields, "monthly_churn_percent")
    return FinancialInputs(
        currency=snapshot.currency or UNKNOWN_CURRENCY,
        monthly_revenue_minor=_int(snapshot.fields, "monthly_revenue_minor"),
        monthly_costs_minor=_int(snapshot.fields, "monthly_costs_minor"),
        cash_on_hand_minor=_int(snapshot.fields, "cash_on_hand_minor"),
        cost_of_revenue_minor=_int(snapshot.fields, "cost_of_revenue_minor"),
        last_12m_revenue_minor=_int(snapshot.fields, "last_12m_revenue_minor"),
        customer_acquisition_cost_minor=_int(
            snapshot.fields, "customer_acquisition_cost_minor"
        ),
        average_revenue_per_customer_minor=_int(
            snapshot.fields, "average_revenue_per_customer_minor"
        ),
        monthly_churn_percent=(
            Decimal(str(churn))
            if isinstance(churn, int | float) and not isinstance(churn, bool)
            else None
        ),
    )


# ---------------------------------------------------------------------------
# Rendering -- what the model is actually shown
# ---------------------------------------------------------------------------


# How each computed figure is written out. A fixed tuple rather than
# `dataclasses.fields()` so the order in the prompt is the order here: the
# rendered string is part of "same input" for T2.9's same-input-same-score, and
# a reflection order that changes with a dataclass edit would move it silently.
_FIGURE_RENDERING: Final[tuple[tuple[str, str], ...]] = (
    ("gross_margin_percent", "percent"),
    ("net_burn_minor", "money"),
    ("runway_months", "months"),
    ("ltv_minor", "money"),
    ("ltv_cac_ratio", "ratio"),
    ("cac_payback_months", "months"),
    ("annual_run_rate_minor", "money"),
    ("run_rate_vs_trailing_percent", "percent"),
)


def _render_metric(metric: Metric, unit: str, currency: str) -> str:
    """One figure, or a named reason it could not be worked out.

    The reason is rendered rather than the line being dropped, because the
    rubric is told to distinguish absent from bad (rule 3 of its prompt) and a
    missing line reads as neither -- it reads as nothing having been checked.
    """
    if metric.reason is not None or metric.value is None:
        reason = metric.reason.value if metric.reason is not None else "missing_input"
        return f"not computable ({reason})"

    value = metric.value
    match unit:
        case "percent":
            return f"{value}%"
        case "months":
            return f"{value} months"
        case "money":
            if currency == UNKNOWN_CURRENCY:
                # Withheld rather than printed against an assumed currency:
                # see UNKNOWN_CURRENCY. The ratios below carry the same
                # information without depending on it.
                return "not shown (the profile does not state a currency)"
            return f"{to_major_units(int(value), currency)} {currency}"
        case _:
            return str(value)


def render_computed_figures(summary: FinancialSummary) -> str:
    """`finance.compute`'s output as the scoring prompt's authoritative block.

    D9: these are the numbers, computed in code, and the rubric is instructed
    not to recalculate one. Rendering is therefore the only place they can be
    distorted, which is why an unknown currency withholds the absolute figures
    instead of guessing at one.
    """
    currency = summary.currency
    lines = [
        f"currency: {currency}"
        if currency != UNKNOWN_CURRENCY
        else "currency: not stated by the founder"
    ]
    for name, unit in _FIGURE_RENDERING:
        metric: Metric = getattr(summary, name)
        lines.append(f"{name}: {_render_metric(metric, unit, currency)}")

    profitable = summary.is_profitable
    lines.append(
        "is_profitable: "
        + ("unknown" if profitable is None else str(profitable).lower())
    )
    return "\n".join(lines)


def render_profile_facts(snapshot: ProfileSnapshot) -> str:
    """The profile as prose the model can read and cite.

    Every field carries **where it came from**, because the rubric is told that
    corroboration beats assertion (rule 4 of its prompt) and cannot apply that
    rule to values it cannot tell apart. A figure the founder typed and the same
    figure read out of their bank statement are different evidence.

    Fields are written in `PROFILE_FIELDS` declaration order, not the JSONB's
    insertion order, so the same profile renders identically however it was
    assembled -- T2.9 compares audits of the same input.
    """
    lines = [f"source_id: {PROFILE_SOURCE_ID}"]

    columns = (
        ("name", snapshot.name),
        ("sector", snapshot.sector),
        ("stage", snapshot.stage.value if snapshot.stage is not None else None),
        ("country", snapshot.country),
        ("currency", snapshot.currency),
    )
    for label, value in columns:
        lines.append(f"{label}: {value if value else 'not stated'}")

    lines.append("")
    lines.append(
        "Fields below are as submitted. Amounts ending in `_minor` are integer "
        "minor units (e.g. kobo, cents) of the currency above."
    )

    for spec in PROFILE_FIELDS:
        value = _value(snapshot.fields, spec.name)
        if value is None or (spec.kind is FieldKind.TEXT and not str(value).strip()):
            continue
        source = _source(snapshot.fields, spec.name)
        attribution = f" [source: {source}]" if source else ""
        lines.append(f"{spec.name}: {value}{attribution}")

    return "\n".join(lines)


def render_benchmark_context(
    matches: Mapping[BenchmarkMetric, audit_service.BenchmarkMatch],
    summary: FinancialSummary,
) -> str:
    """Matched benchmark bands, and how well each one actually matched.

    **An empty string is the correct output when nothing matched** and must
    never be filled with a plausible default (D11) -- `rubric.v1.score` already
    turns it into "None matched, reason from first principles and lower your
    confidence", which is the honest instruction.

    `quartile_position` is computed here rather than asked for: where a value
    sits in a band is arithmetic, and it reads differently per metric (above p75
    is excellent for gross margin and poor for CAC payback).
    """
    blocks = []
    # Enum declaration order, not `matches`' insertion order -- see T2.9.
    for metric in BenchmarkMetric:
        match = matches.get(metric)
        if match is None:
            continue
        band = match.benchmark
        direction = (
            "higher is better" if higher_is_better(metric) else "lower is better"
        )
        line = (
            f"{metric.value}: p25 {band.p25}, p50 {band.p50}, p75 {band.p75} "
            f"({direction}). Peer group: sector {band.sector}, stage "
            f"{band.stage.value}, region {band.region}. Match quality: "
            f"{match.quality.value}. Source: {band.source}, as of "
            f"{band.as_of_date.isoformat()}."
        )
        value: Metric = getattr(summary, metric.value)
        if value.value is not None:
            position = quartile_position(
                value.value, band.p25, band.p50, band.p75, metric
            )
            line += f" This startup sits in the {position} of that band."
        if match.quality is MatchQuality.BROAD:
            line += (
                " This is an all-sectors global band and is weak evidence; "
                "treat it as context, not as a peer comparison."
            )
        blocks.append(line)

    return "\n".join(blocks)


async def assemble_benchmark_context(
    session: AsyncSession,
    snapshot: ProfileSnapshot,
    summary: FinancialSummary,
) -> str:
    """Look up a band for every figure that has a value, and render them.

    The only part of the pipeline that needs a database, split out for that
    reason -- see the module docstring.

    **Stage is matched exactly** by `lookup_benchmark`, so a profile with no
    stage has no possible peer group and returns the empty string rather than
    being compared against a stage it never claimed. Metrics whose value could
    not be computed are not looked up at all: a band for a figure we do not have
    is a comparison the model cannot make and an invitation to imagine one.
    """
    if snapshot.stage is None:
        return ""

    matches: dict[BenchmarkMetric, audit_service.BenchmarkMatch] = {}
    for metric in BenchmarkMetric:
        value: Metric = getattr(summary, metric.value)
        if not value.known:
            continue
        found = await audit_service.lookup_benchmark(
            session,
            sector=snapshot.sector or ANY_SECTOR,
            stage=snapshot.stage,
            metric=metric,
            region=snapshot.country or GLOBAL_REGION,
        )
        if found is not None:
            matches[metric] = found

    return render_benchmark_context(matches, summary)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _as_finding(contradiction: Contradiction) -> Finding:
    """A model-found contradiction in the same shape as an arithmetic one.

    `LIKELY`, never `CERTAIN`: this half is a judgement and can be a false
    positive, unlike a head-count impossibility. Its founder-facing `summary` is
    already written to assume a mistake rather than deception, so it becomes the
    `message` unchanged.

    Scoring does **not** go through here -- `data_integrity_score` takes
    contradictions as their own argument with their own penalty, so passing the
    converted findings to it as well would charge for each one twice.
    """
    return Finding(
        code=FindingCode.CONTRADICTION,
        severity=Severity.LIKELY,
        fields=(),
        message=contradiction.summary,
        detail=(
            f"{contradiction.claim.source_id}: "
            f"{contradiction.claim.quote!r} vs "
            f"{contradiction.conflicting_claim.source_id}: "
            f"{contradiction.conflicting_claim.quote!r}"
        ),
    )


def _with_unanswered_dimensions(
    scores: Sequence[v1.DimensionScore],
) -> list[v1.DimensionScore]:
    """Fill in every in-scope dimension the scoring pass did not return.

    **This is the difference between a verdict and a false verdict.** Synthesis
    measures coverage as evidenced dimensions over the dimensions it was *given*
    -- so an assessment that comes back with one dimension out of eleven reads
    as fully covered, and a single high score becomes "fundable". That is
    exactly the failure `CLAUDE.md` section 5 names as a guarantee. T2.7's own
    tests cannot see it because their fixtures always build the complete set;
    here the completeness is a model's promise rather than a fixture's.

    A dimension nobody scored is a dimension with no data, so it is padded as
    `insufficient_data` rather than the denominator being adjusted. That also
    puts it in the founder's `unevidenced_dimensions` and near the top of the
    action plan, instead of vanishing from the report as though it had never
    been in scope.

    Padded in `dimensions_for` order so the output does not depend on what the
    model happened to return first (T2.9).
    """
    answered = {score.dimension for score in scores}
    padded = list(scores)
    padded.extend(
        v1.DimensionScore(
            dimension=spec.key,
            score=0,
            rationale=(
                "The scoring pass returned no entry for this dimension, so it "
                "has not been assessed."
            ),
            sufficiency=DataSufficiency.INSUFFICIENT_DATA,
            citations=[],
        )
        for spec in v1.dimensions_for(_SCOPE)
        if spec.key not in answered
    )
    return padded


async def run_pipeline(
    client: AiClient,
    *,
    snapshot: ProfileSnapshot,
    documents: Sequence[UntrustedContent] = (),
    benchmark_context: str = "",
    user_id: str | None = None,
) -> AuditReport:
    """Stages 2-5 over one profile, ending in a report.

    Stage 1 (extraction) belongs to the caller once storage exists (T2.4a);
    stage 6 (persistence) belongs to the service, which owns the AuditRun row
    and its fingerprint.

    Two calls are deliberately conditional, and both conditions are about not
    paying for an answer that is already known:

    * **Contradiction detection is skipped without documents.** Its whole job is
      disagreement *between* sources -- a deck claiming 34 customers against
      financials showing 12. With one source there is nothing to compare, and
      the arithmetic half (`check_scale`, `check_team`) has already run.
    * **Scoring is skipped below `INTEGRITY_FLOOR`.** `synthesise` returns
      `insufficient_data` on both verdicts at that point *regardless of the
      scores*, so the rubric call -- `claude-opus-5` at high effort against a
      16k budget, the most expensive call the platform makes (D16) -- would buy
      a verdict that was already decided. The founder is told to fix the
      contradictions instead, which is the same answer sooner and for nothing.
      That path passes **no** scores rather than a padded set of unassessed
      ones: nothing here was left unevidenced, and listing every dimension as
      such would tell the founder they submitted nothing when what they
      submitted disagreed with itself. The findings say which figures, and the
      verdict's own rationale says why.
    """
    inputs = financial_inputs(snapshot)
    summary = compute(inputs)

    findings = [
        *check_scale(
            inputs, active_customers=_int(snapshot.fields, "active_customers")
        ),
        *check_team(
            team_size=_int(snapshot.fields, "team_size"),
            founder_count=_int(snapshot.fields, "founder_count"),
            founders_full_time=_int(snapshot.fields, "founders_full_time"),
        ),
    ]

    profile_facts = render_profile_facts(snapshot)

    contradictions: list[Contradiction] = []
    if documents:
        found = await find_contradictions(
            client,
            profile_facts=profile_facts,
            documents=documents,
            user_id=user_id,
        )
        contradictions = list(found.output.contradictions)

    integrity = data_integrity_score(findings, contradictions)
    reported = (*findings, *(_as_finding(c) for c in contradictions))

    if integrity < INTEGRITY_FLOOR:
        logger.info(
            "audit scoring skipped",
            extra={
                "context": {
                    "reason": "data_integrity_below_floor",
                    # `log_context()` and not the findings themselves: the
                    # founder may see their own figures, a shared log may not
                    # (`CLAUDE.md` section 4).
                    "findings": [finding.log_context() for finding in reported],
                }
            },
        )
        return synthesise(
            rubric_version=v1.RUBRIC_VERSION,
            scores=(),
            data_integrity_score=integrity,
            findings=reported,
        )

    assessment = await v1.score(
        client,
        computed_figures=render_computed_figures(summary),
        profile_facts=profile_facts,
        documents=documents,
        benchmark_context=benchmark_context,
        scope=_SCOPE,
        user_id=user_id,
    )

    return synthesise(
        # The rubric version this run was scored against is the one this code
        # asked for, not the one the model echoed back (D12). A run has to stay
        # explainable, and a mislabelled version attributes the wrong criteria
        # to a founder's verdict.
        rubric_version=v1.RUBRIC_VERSION,
        scores=_with_unanswered_dimensions(assessment.output.scores),
        data_integrity_score=integrity,
        findings=reported,
    )
