"""Read `companies.json` into typed fixtures.

Deliberately strict: an unknown stage, verdict level, or finding code raises
here rather than surfacing later as a mysteriously-never-matching expectation.
A golden set that silently ignores a typo in an expected value is worse than no
golden set, because the eval report still prints a pass.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

from app.modules.audit.consistency import FindingCode
from app.modules.audit.pipeline import ProfileSnapshot
from app.modules.audit.rubric.v1 import Dimension
from app.modules.audit.synthesis import VerdictLevel
from app.modules.intake.fields import Stage

_SOURCE: Final = Path(__file__).resolve().parent / "companies.json"

EVIDENCE_FIELDS: Final[dict[Dimension, tuple[str, ...]]] = {
    Dimension.FINANCIAL_HEALTH: (
        "monthly_revenue_minor",
        "monthly_costs_minor",
        "cash_on_hand_minor",
        "cost_of_revenue_minor",
    ),
    Dimension.UNIT_ECONOMICS: (
        "customer_acquisition_cost_minor",
        "average_revenue_per_customer_minor",
        "monthly_churn_percent",
        "active_customers",
    ),
    Dimension.TRACTION: (
        "monthly_revenue_minor",
        "last_12m_revenue_minor",
        "active_customers",
        "monthly_active_users",
    ),
    Dimension.MARKET_OPPORTUNITY: ("market_size_note", "competition_note"),
    Dimension.TEAM: (
        "team_size",
        "founder_count",
        "founders_full_time",
        "key_person_dependency",
    ),
    Dimension.LEGAL_AND_IP: ("ip_owned", "contracts_transferable", "cap_table_summary"),
    Dimension.DATA_INTEGRITY: (
        "monthly_revenue_minor",
        "monthly_costs_minor",
        "cash_on_hand_minor",
    ),
    # `current_raise_target_minor` is deliberately NOT here. How much a founder
    # wants is not evidence that capital would produce output rather than cost;
    # it becomes meaningful only alongside `use_of_funds`, which names what the
    # money buys. Counting the amount on its own would let a profile that
    # answered nothing about growth read as evidenced -- the same over-generosity
    # that keeps `description` out of this table.
    Dimension.SCALABILITY: ("growth_constraint", "use_of_funds"),
    Dimension.OWNER_INDEPENDENCE: (
        "key_person_dependency",
        "team_size",
        "founders_full_time",
    ),
    Dimension.TRANSFERABILITY: ("contracts_transferable", "ip_owned"),
    Dimension.REVENUE_DURABILITY: (
        "active_customers",
        "average_revenue_per_customer_minor",
        "monthly_churn_percent",
    ),
}
"""Which profile fields could be cited for each rubric dimension.

A reading of `rubric/v1`'s criteria against `intake/fields.py`, used to answer a
question about the *fixtures* -- does this profile supply anything at all for
this dimension? -- with no model call and no guess about what a model would do.

**`description` and `business_model` are deliberately absent.** Every profile
has both, so counting them would make the answer "yes" for every dimension of
every company and the check would assert nothing.

`MARKET_OPPORTUNITY` and `SCALABILITY` mapped to **nothing** until 2026-08-03,
and that emptiness was the finding: their criteria ask for market sizing,
competition, a named capital constraint and a capital plan, and the form asked
for none of it. Both now have real fields, so this table no longer needs the
length-proxy workaround it carried while the substance lived in free prose.

One criterion is still unserved: scalability wants the marginal-cost trend
("delivery cost per additional customer is falling, flat, or rising -- and
which it is, is evidenced"), which no field asks for. Proposed in
`FOUNDER-ONBOARDING.md` rather than added, because it is a form change and that
is the owner's call.
"""


@dataclass(frozen=True, slots=True)
class ExpectedVerdict:
    """What one verdict should come out as.

    The score is a band rather than a number on purpose. A model-derived
    dimension score is not reproducible to the unit, so asserting equality would
    make the harness fail on noise and teach everyone to ignore it. `None` on
    both bounds means no score is expected at all -- which is the correct
    expectation for `insufficient_data`, where inventing one to fill the gap is
    exactly what `Verdict.score` documents it will not do.
    """

    level: VerdictLevel
    score_min: int | None
    score_max: int | None

    def accepts(self, level: VerdictLevel, score: int | None) -> bool:
        if level is not self.level:
            return False
        if self.score_min is None and self.score_max is None:
            return score is None
        if score is None:
            return False
        low = self.score_min if self.score_min is not None else 0
        high = self.score_max if self.score_max is not None else 100
        return low <= score <= high


class ReviewedBy(StrEnum):
    """Whose judgement an expectation is. An eval report must print this.

    The distinction is the difference between an accuracy measurement and a
    consistency check wearing an accuracy costume, and it is not visible in the
    numbers themselves -- only here.
    """

    DETERMINISTIC = "deterministic"
    """Follows from arithmetic in `synthesis.py`. Nobody's judgement is in it."""

    ASSISTANT_DRAFT = "assistant-draft"
    """Scored by Claude against the published rubric, at the owner's explicit
    instruction. Stronger than unreviewed, weaker than an analyst: the same
    model family scored the fixture and will be scored against it."""

    HUMAN = "human"
    """An analyst read the profile and decided. The only unqualified ground
    truth this file can hold."""


@dataclass(frozen=True, slots=True)
class GoldenCompany:
    """One hand-scored company."""

    id: str
    why_this_case: str
    reviewed: bool
    reviewed_by: ReviewedBy
    verdict_is_model_dependent: bool
    saleability_below_fundability: bool
    """Whether this company's claim is the *gap* between the two verdicts.

    Set on the fixture that exists to prove the verdicts can diverge. Bands
    alone cannot carry that claim -- two overlapping bands are both satisfied
    by a run that scored the two verdicts identically, which is precisely the
    failure the fixture is meant to catch. The accuracy half must compare the
    observed scores directly wherever this is set.
    """
    snapshot: ProfileSnapshot
    fundability: ExpectedVerdict
    saleability: ExpectedVerdict
    data_integrity_min: Decimal
    data_integrity_max: Decimal
    must_flag: tuple[FindingCode, ...]

    def integrity_accepts(self, score: Decimal) -> bool:
        return self.data_integrity_min <= score <= self.data_integrity_max

    def evidence_for(self, dimension: Dimension) -> tuple[str, ...]:
        """The fields this profile actually supplies for one dimension.

        Empty means the profile says nothing a score on that dimension could
        cite -- which, per `_verdict_for`, forces the whole verdict to
        `provisional` however good the rest of the submission is.
        """
        present = []
        for name in EVIDENCE_FIELDS[dimension]:
            raw = self.snapshot.fields.get(name)
            value = raw.get("value") if isinstance(raw, dict) else raw
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            present.append(name)
        return tuple(present)


def _verdict(raw: Mapping[str, Any]) -> ExpectedVerdict:
    return ExpectedVerdict(
        level=VerdictLevel(raw["level"]),
        score_min=raw["score_min"],
        score_max=raw["score_max"],
    )


def _company(raw: Mapping[str, Any]) -> GoldenCompany:
    profile = raw["profile"]
    expected = raw["expected"]
    return GoldenCompany(
        id=raw["id"],
        why_this_case=raw["why_this_case"],
        reviewed=expected["reviewed"],
        reviewed_by=ReviewedBy(expected["reviewed_by"]),
        verdict_is_model_dependent=raw["verdict_is_model_dependent"],
        # Optional, unlike everything else here: it is a claim only one fixture
        # makes, and requiring `false` on the other seven would be noise that
        # obscures the one company where it means something.
        saleability_below_fundability=expected.get(
            "saleability_below_fundability", False
        ),
        snapshot=ProfileSnapshot(
            fields=profile["fields"],
            name=profile["name"],
            sector=profile["sector"],
            stage=Stage(profile["stage"]),
            country=profile["country"],
            currency=profile["currency"],
        ),
        fundability=_verdict(expected["fundability"]),
        saleability=_verdict(expected["saleability"]),
        data_integrity_min=Decimal(str(expected["data_integrity_min"])),
        data_integrity_max=Decimal(str(expected["data_integrity_max"])),
        must_flag=tuple(FindingCode(code) for code in expected["must_flag"]),
    )


@lru_cache(maxsize=1)
def load_companies() -> tuple[GoldenCompany, ...]:
    """Every company in the set, reviewed or not.

    Cached because the file is immutable for the life of a test session and the
    parse is pure. Ids are asserted unique here: two companies sharing an id
    would silently collapse into one row in the eval report.
    """
    document = json.loads(_SOURCE.read_text(encoding="utf-8"))
    companies = tuple(_company(entry) for entry in document["companies"])

    ids = [company.id for company in companies]
    duplicates = {name for name in ids if ids.count(name) > 1}
    if duplicates:
        raise ValueError(f"duplicate golden company ids: {sorted(duplicates)}")

    return companies


def reviewed_companies() -> tuple[GoldenCompany, ...]:
    """The companies somebody has actually scored.

    The accuracy half of T2.9 must run against these and nothing else. Measuring
    the pipeline against an unreviewed expectation measures whether it agrees
    with whoever drafted the fixture, then reports the result as accuracy --
    the same false-confidence shape as a green suite over an untested path.

    **Every company currently passes this filter**, and the determinism suite
    asserts they do -- a fixture added with `reviewed: false` is rejected there
    rather than skipped here. Two defences for one rule is deliberate: this one
    is what the accuracy half calls, and it must keep working if the other is
    ever relaxed.

    **Being in this tuple is not the same as being ground truth.** Check
    `reviewed_by`: `HUMAN` is the only value that makes an agreement figure a
    plain accuracy number. `DETERMINISTIC` is not a measurement of the model at
    all -- those verdicts never reach it -- and `ASSISTANT_DRAFT` is the same
    model family on both sides of the comparison. `qualified_ids()` exists so a
    report cannot omit that caveat by accident.
    """
    return tuple(company for company in load_companies() if company.reviewed)


def qualified_ids() -> dict[ReviewedBy, list[str]]:
    """Company ids grouped by whose judgement scored them.

    For the eval report's header. A single agreement percentage over a mixed
    set means three different things at once and reads as one.
    """
    grouped: dict[ReviewedBy, list[str]] = {source: [] for source in ReviewedBy}
    for company in reviewed_companies():
        grouped[company.reviewed_by].append(company.id)
    return grouped


def as_ids(companies: Sequence[GoldenCompany]) -> list[str]:
    """`pytest.mark.parametrize` ids, so a failure names the company."""
    return [company.id for company in companies]
