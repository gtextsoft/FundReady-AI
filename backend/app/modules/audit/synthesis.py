"""Stage 5 of the audit pipeline: scores to verdicts, report, and action plan (T2.7).

Layer: **service** (ARCHITECTURE.md section 3). Pure: no I/O, no model call.

**The verdict is computed, not asked for.** Every input here already came from a
model -- the rubric scored each dimension and cited its evidence -- but turning
those scores into "fundable" or "not yet" is arithmetic over a documented rule,
because the verdict is the product's central claim. Three reasons it cannot be a
second opinion:

* T2.9 requires the same input to produce the same verdict. A model asked twice
  may not agree with itself.
* A founder who is told "not yet" is owed the reason. A rule can be shown to
  them; a judgement cannot.
* `CLAUDE.md` section 5 forbids a false "fundable" on thin data. That is a
  guarantee, and a guarantee has to be enforced by something that cannot be
  talked out of it.

**Thin data never yields a confident verdict.** Sufficiency is tracked
separately from score throughout (`DataSufficiency`), so a dimension that scored
badly and a dimension nobody submitted evidence for stay distinguishable all the
way to the verdict. Collapsing them is the exact failure the rubric's
`sufficiency` field exists to prevent, and it would be invisible in the output.

**Everything traces back.** A verdict cites the dimensions that drove it; each
dimension already carries its own citations to submitted data (T2.4) and its
data-integrity context (T2.5). Nothing is asserted here that cannot be followed
back to something a founder actually submitted.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Final

from app.ai.schemas import DataSufficiency
from app.modules.audit.consistency import Finding
from app.modules.audit.rubric.v1 import Dimension, DimensionScore, Scope, dimensions_for

__all__ = [
    "READY_THRESHOLD",
    "ActionItem",
    "AuditReport",
    "Verdict",
    "VerdictLevel",
    "synthesise",
]

READY_THRESHOLD: Final = 70
"""Mean in-scope score at or above which a verdict reads `ready`.

A round number, and deliberately not tuned: no golden set exists yet (T2.9), so
any more precise figure would be false precision dressed as rigour. Revisit it
against hand-scored companies, not against intuition.
"""

_MIN_SUFFICIENT_RATIO: Final = Decimal("0.5")
"""Below this share of in-scope dimensions carrying real evidence, no verdict.

Half is a judgement, but the direction is not: `CLAUDE.md` section 5 says thin
data yields `insufficient-data`, never a confident answer, so the failure mode
this guards against is one-sided.
"""

_INTEGRITY_FLOOR: Final = Decimal(50)
"""Below this `data_integrity_score`, no verdict is offered at all.

If the submitted figures contradict each other badly enough, scoring them is
scoring noise. Better to tell the founder to fix the data than to hand them a
verdict derived from numbers we already believe are wrong.
"""


class VerdictLevel(StrEnum):
    """What the audit is prepared to say."""

    READY = "ready"
    """Meets the bar on well-evidenced dimensions."""

    NOT_YET = "not_yet"
    """Enough evidence to judge, and it does not meet the bar."""

    PROVISIONAL = "provisional"
    """A conclusion is offered but the evidence is partial. Must be presented
    as provisional wherever it is shown -- never rendered as a plain result."""

    INSUFFICIENT_DATA = "insufficient_data"
    """No conclusion. Not a failure -- an absence. Never render this as
    'not fundable': the founder has not been assessed and told otherwise."""


@dataclass(frozen=True, slots=True)
class ActionItem:
    """One thing the founder can do to improve the verdict.

    Derived from a dimension's `unmet_criteria`, which the rubric is instructed
    to write as actions for exactly this reason: a criterion phrased as a
    judgement produces a task nobody can complete.
    """

    dimension: Dimension
    action: str
    dimension_score: int | None
    """The score that produced this item, or `None` when the dimension was
    unscoreable. Used to order the plan worst-first, not shown as a grade."""


@dataclass(frozen=True, slots=True)
class Verdict:
    """One verdict -- fundability or saleability."""

    scope: Scope
    level: VerdictLevel
    score: int | None
    """Mean of the well-evidenced in-scope dimensions, or `None` when there
    were too few to mean anything. Never invented to fill the gap."""

    sufficiency: DataSufficiency
    evidenced_dimensions: tuple[Dimension, ...]
    unevidenced_dimensions: tuple[Dimension, ...]
    rationale: str
    """Founder-facing. Says what the verdict is and, when it is not `ready`,
    what would change it."""


@dataclass(frozen=True, slots=True)
class AuditReport:
    """Everything one audit concluded."""

    fundability: Verdict
    saleability: Verdict
    data_integrity_score: Decimal
    findings: tuple[Finding, ...]
    action_plan: tuple[ActionItem, ...]
    rubric_version: str


def _verdict_for(
    scope: Scope,
    scores: Sequence[DimensionScore],
    *,
    integrity: Decimal,
) -> Verdict:
    """Reduce the in-scope dimensions to one verdict."""
    in_scope_keys = {spec.key for spec in dimensions_for(scope)}
    relevant = [score for score in scores if score.dimension in in_scope_keys]

    evidenced = [
        score
        for score in relevant
        if score.sufficiency is not DataSufficiency.INSUFFICIENT_DATA
    ]
    unevidenced = tuple(
        score.dimension
        for score in relevant
        if score.sufficiency is DataSufficiency.INSUFFICIENT_DATA
    )

    if integrity < _INTEGRITY_FLOOR:
        return Verdict(
            scope=scope,
            level=VerdictLevel.INSUFFICIENT_DATA,
            score=None,
            sufficiency=DataSufficiency.INSUFFICIENT_DATA,
            evidenced_dimensions=tuple(s.dimension for s in evidenced),
            unevidenced_dimensions=unevidenced,
            rationale=(
                "The figures submitted do not agree with each other well enough "
                "to score. Resolving the flagged inconsistencies will let this "
                "audit run properly — no verdict has been formed."
            ),
        )

    covered = (
        Decimal(len(evidenced)) / Decimal(len(relevant)) if relevant else Decimal(0)
    )

    if not evidenced or covered < _MIN_SUFFICIENT_RATIO:
        return Verdict(
            scope=scope,
            level=VerdictLevel.INSUFFICIENT_DATA,
            score=None,
            sufficiency=DataSufficiency.INSUFFICIENT_DATA,
            evidenced_dimensions=tuple(s.dimension for s in evidenced),
            unevidenced_dimensions=unevidenced,
            rationale=(
                "Not enough evidence to assess this yet. Adding information on "
                "the areas listed as unevidenced will allow a verdict. This is "
                "not a negative result — the assessment has not been made."
            ),
        )

    mean = sum(score.score for score in evidenced) // len(evidenced)
    thin = unevidenced or any(
        score.sufficiency is DataSufficiency.PROVISIONAL for score in evidenced
    )

    if thin:
        level = VerdictLevel.PROVISIONAL
        sufficiency = DataSufficiency.PROVISIONAL
        rationale = (
            f"Provisional: scored {mean} out of 100 on the evidence available, "
            "but some areas are still thin. Filling the gaps below could move "
            "this in either direction."
        )
    elif mean >= READY_THRESHOLD:
        level = VerdictLevel.READY
        sufficiency = DataSufficiency.SUFFICIENT
        rationale = f"Scored {mean} out of 100 across all assessed areas."
    else:
        level = VerdictLevel.NOT_YET
        sufficiency = DataSufficiency.SUFFICIENT
        rationale = (
            f"Scored {mean} out of 100, below the {READY_THRESHOLD} needed. "
            "The action plan lists what would raise it."
        )

    return Verdict(
        scope=scope,
        level=level,
        score=mean,
        sufficiency=sufficiency,
        evidenced_dimensions=tuple(s.dimension for s in evidenced),
        unevidenced_dimensions=unevidenced,
        rationale=rationale,
    )


def _action_plan(scores: Sequence[DimensionScore]) -> tuple[ActionItem, ...]:
    """Unmet criteria, worst-scoring dimension first.

    Ordered so a founder with limited time works on what is holding them back
    most. Unscoreable dimensions sort first: "we could not assess this" is more
    urgent than "this scored 40", because it is cheaper to fix and it blocks
    the verdict itself.
    """
    items: list[ActionItem] = []
    for score in scores:
        unscoreable = score.sufficiency is DataSufficiency.INSUFFICIENT_DATA
        for action in score.unmet_criteria:
            items.append(
                ActionItem(
                    dimension=score.dimension,
                    action=action,
                    dimension_score=None if unscoreable else score.score,
                )
            )

    return tuple(
        sorted(
            items,
            key=lambda item: (
                item.dimension_score is not None,
                item.dimension_score if item.dimension_score is not None else 0,
                item.dimension.value,
            ),
        )
    )


def synthesise(
    *,
    rubric_version: str,
    scores: Sequence[DimensionScore],
    data_integrity_score: Decimal = Decimal(100),
    findings: Sequence[Finding] = (),
) -> AuditReport:
    """Turn scored dimensions into two verdicts, a report, and an action plan.

    `scores` comes from `rubric.v1.score`; `data_integrity_score` and `findings`
    from `audit.consistency`. Nothing here calls a model -- see the module
    docstring for why the verdict must be a rule rather than a judgement.
    """
    return AuditReport(
        fundability=_verdict_for(
            Scope.FUNDABILITY, scores, integrity=data_integrity_score
        ),
        saleability=_verdict_for(
            Scope.SALEABILITY, scores, integrity=data_integrity_score
        ),
        data_integrity_score=data_integrity_score,
        findings=tuple(findings),
        action_plan=_action_plan(scores),
        rubric_version=rubric_version,
    )
