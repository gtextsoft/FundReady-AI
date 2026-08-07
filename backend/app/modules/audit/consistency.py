"""Stage 2 of the audit pipeline: does the submitted data agree with itself (T2.5)?

Layer: **service** (ARCHITECTURE.md section 3). Pure over its inputs; no I/O
beyond the one model call in `find_contradictions`.

**Two mechanisms, deliberately not merged.**

*Scale plausibility* is arithmetic and lives in code. `monthly_revenue_minor x
12` either agrees with `last_12m_revenue_minor` within an order of magnitude or
it does not, and D9 is explicit that money is math rather than opinion. Handing
that to a model would also make T2.9's same-input-same-score requirement
impossible, because the answer would move between runs.

*Contradictions* are semantic -- a deck claiming 34 customers against
financials showing 12 -- and only a reader can see them. That is the model's
half, and it must cite both sides.

**Thresholds are deliberately loose.** Only order-of-magnitude discrepancies
(10x) are reported, never 2x ones. Telling a founder their revenue looks wrong
when it is right damages trust in the entire audit far more than missing one
subtle error does, and this score feeds a verdict about their company. A
finding here should be something a human would also call obviously wrong.

**Two audiences, two messages.** Every finding carries a `message` written for
the founder -- plain, specific, and actionable -- and a `detail` written for
whoever is debugging. `log_context()` returns neither: only the code and the
field names, because `CLAUDE.md` section 4 forbids putting financial figures in
logs. Showing a founder their own numbers is not a leak; writing them to a log
shared by every tenant is.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Final

from anthropic.types import MessageParam
from pydantic import Field

from app.ai.caching import cached_system
from app.ai.client import AiClient, AiResult, ModelTier
from app.ai.guards import UNTRUSTED_RULE, UntrustedContent
from app.ai.prompts import PromptVersion, register
from app.ai.schemas import Citation, StructuredOutput
from app.modules.audit.finance import FinancialInputs

__all__ = [
    "CONTRADICTION_PROMPT",
    "Contradiction",
    "ContradictionReport",
    "Finding",
    "FindingCode",
    "Severity",
    "check_entity",
    "check_scale",
    "check_team",
    "data_integrity_score",
    "find_contradictions",
]

_ORDER_OF_MAGNITUDE: Final = Decimal(10)
"""The discrepancy factor a finding needs before it is reported.

Ten, not two. See the module docstring: a false positive costs more than a
missed subtlety, because the founder stops believing the audit.
"""

_IMPLAUSIBLE_CHURN_PERCENT: Final = Decimal("0.1")
"""Monthly churn below this reads as a decimal-point error.

`0.02` meaning 2% is indistinguishable from a genuine 0.02% by range alone
(T2.2a), but 0.02% monthly is a quarter of a percent a year -- effectively no
churn at all. Businesses like that exist; they are rare enough to be worth a
question rather than a silent pass into an LTV that is 100x too high.
"""


class Severity(StrEnum):
    """How much doubt a finding casts."""

    CERTAIN = "certain"
    """Arithmetically impossible. Not a heuristic -- these cannot be false."""

    LIKELY = "likely"
    """Crossed a threshold. Probably wrong, but a real business could look
    like this, so the wording must leave room for the founder to be right."""


class FindingCode(StrEnum):
    """Stable, machine-readable codes. Clients branch on these, not on prose."""

    REVENUE_VS_ANNUAL = "revenue_vs_annual"
    REVENUE_VS_CUSTOMERS = "revenue_vs_customers"
    CHURN_IMPLAUSIBLY_LOW = "churn_implausibly_low"
    COST_EXCEEDS_REVENUE_IMPLAUSIBLY = "cost_exceeds_revenue_implausibly"
    MORE_FOUNDERS_THAN_TEAM = "more_founders_than_team"
    MORE_FULL_TIME_THAN_FOUNDERS = "more_full_time_than_founders"
    INCORPORATED_AFTER_TRADING = "incorporated_after_trading"
    CONTRADICTION = "contradiction"


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing that does not add up.

    `message` is shown to the founder. `detail` is for whoever is debugging.
    Neither goes in a log -- use `log_context()`.
    """

    code: FindingCode
    severity: Severity
    fields: tuple[str, ...]
    message: str
    """Founder-facing. Names the fields, says what looks wrong, and says what
    to do about it. Never accusatory: the founder is far more likely to have
    mistyped a unit than to be lying, and the wording should assume that."""

    detail: str
    """Engineer-facing. The comparison that fired, so a support conversation
    does not require re-deriving it."""

    def log_context(self) -> dict[str, Any]:
        """What is safe to log: the code and which fields, never the values.

        `CLAUDE.md` section 4 forbids financial figures in logs. The founder
        may see their own numbers; a log read by operators and shipped to a
        third-party aggregator may not.
        """
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "fields": list(self.fields),
        }


# ---------------------------------------------------------------------------
# Scale plausibility -- arithmetic, no model (D9)
# ---------------------------------------------------------------------------


def _off_by_an_order_of_magnitude(left: Decimal, right: Decimal) -> bool:
    """True when the two differ by 10x or more in either direction."""
    if left <= 0 or right <= 0:
        return False
    high, low = (left, right) if left > right else (right, left)
    return high / low >= _ORDER_OF_MAGNITUDE


def check_scale(
    inputs: FinancialInputs, *, active_customers: int | None = None
) -> list[Finding]:
    """Cross-field arithmetic checks over the submitted figures.

    Every check is skipped unless *both* of its inputs are present -- a
    half-known profile is the normal case (`intake/fields.py`), and a missing
    figure is a gap for the rubric to note, never a contradiction.
    """
    findings: list[Finding] = []

    monthly = inputs.monthly_revenue_minor
    annual = inputs.last_12m_revenue_minor

    if monthly is not None and annual is not None and monthly > 0 and annual > 0:
        implied = Decimal(monthly) * 12
        if _off_by_an_order_of_magnitude(implied, Decimal(annual)):
            findings.append(
                Finding(
                    code=FindingCode.REVENUE_VS_ANNUAL,
                    severity=Severity.LIKELY,
                    fields=("monthly_revenue_minor", "last_12m_revenue_minor"),
                    message=(
                        "Your monthly revenue multiplied by 12 is very different "
                        "from the last-12-months revenue you entered. One of the "
                        "two is probably in the wrong units — for example whole "
                        "naira where the field expects kobo. Please check both "
                        "figures; the audit uses them for runway and growth."
                    ),
                    detail=(
                        "monthly_revenue_minor * 12 differs from "
                        "last_12m_revenue_minor by >=10x"
                    ),
                )
            )

    arpu = inputs.average_revenue_per_customer_minor

    if (
        monthly is not None
        and arpu is not None
        and active_customers is not None
        and monthly > 0
        and arpu > 0
        and active_customers > 0
    ):
        implied = Decimal(arpu) * active_customers
        if _off_by_an_order_of_magnitude(implied, Decimal(monthly)):
            findings.append(
                Finding(
                    code=FindingCode.REVENUE_VS_CUSTOMERS,
                    severity=Severity.LIKELY,
                    fields=(
                        "monthly_revenue_minor",
                        "active_customers",
                        "average_revenue_per_customer_minor",
                    ),
                    message=(
                        "Your customer count multiplied by your average revenue "
                        "per customer does not come close to your monthly "
                        "revenue. Please check these three figures — the most "
                        "common cause is one of the money fields being entered "
                        "in whole currency units instead of the smallest unit."
                    ),
                    detail=(
                        "active_customers * average_revenue_per_customer_minor "
                        "differs from monthly_revenue_minor by >=10x"
                    ),
                )
            )

    churn = inputs.monthly_churn_percent

    if churn is not None and Decimal(0) < churn < _IMPLAUSIBLE_CHURN_PERCENT:
        # Cross-checked against customer count, not judged on range alone --
        # which is the whole point of doing this here rather than at the field
        # boundary (T2.2a). At 50,000 customers a genuine 0.02% is ten people a
        # month: a real, measurable number. At 34 customers it is 0.0068 people
        # a month, which nobody measured -- it is a mistyped 2%. The test is
        # therefore "does this rate describe less than one customer?", not
        # "is this rate small?".
        implied_customers_lost = (
            churn / 100 * active_customers if active_customers is not None else None
        )
        measurable = (
            implied_customers_lost is not None and implied_customers_lost >= Decimal(1)
        )
        if not measurable:
            findings.append(
                Finding(
                    code=FindingCode.CHURN_IMPLAUSIBLY_LOW,
                    severity=Severity.LIKELY,
                    fields=(
                        ("monthly_churn_percent", "active_customers")
                        if active_customers is not None
                        else ("monthly_churn_percent",)
                    ),
                    message=(
                        "Your monthly churn is under 0.1%, which at your customer "
                        "count would mean fewer than one customer leaves per "
                        "month. If you meant 2% rather than 0.02, please enter it "
                        "as 2 — this field is a percentage, not a fraction. Churn "
                        "drives the lifetime-value figure, so a decimal point "
                        "here changes the result a great deal."
                    ),
                    detail=(
                        "monthly_churn_percent below 0.1 and implies <1 customer "
                        "lost per month -- fraction-entered-as-percent; inflates "
                        "LTV by ~100x (T2.2a)"
                    ),
                )
            )

    cost_of_revenue = inputs.cost_of_revenue_minor

    if (
        monthly is not None
        and cost_of_revenue is not None
        and monthly > 0
        and cost_of_revenue > 0
        and Decimal(cost_of_revenue) / Decimal(monthly) >= _ORDER_OF_MAGNITUDE
    ):
        findings.append(
            Finding(
                code=FindingCode.COST_EXCEEDS_REVENUE_IMPLAUSIBLY,
                severity=Severity.LIKELY,
                fields=("monthly_revenue_minor", "cost_of_revenue_minor"),
                message=(
                    "Your cost of revenue is more than ten times your monthly "
                    "revenue. That can be genuine for a business in early "
                    "production, but it is more often a units mismatch between "
                    "the two fields. Please confirm both."
                ),
                detail="cost_of_revenue_minor >= 10x monthly_revenue_minor",
            )
        )

    return findings


def check_team(
    *,
    team_size: int | None = None,
    founder_count: int | None = None,
    founders_full_time: int | None = None,
) -> list[Finding]:
    """Head-count impossibilities.

    Separate from `check_scale` because these are `CERTAIN`, not heuristic:
    there is no business in which more people founded a company than work at
    it. No threshold, no false positives.
    """
    findings: list[Finding] = []

    if (
        team_size is not None
        and founder_count is not None
        and founder_count > team_size
    ):
        findings.append(
            Finding(
                code=FindingCode.MORE_FOUNDERS_THAN_TEAM,
                severity=Severity.CERTAIN,
                fields=("team_size", "founder_count"),
                message=(
                    "You have listed more founders than total team members. "
                    "Team size should include the founders, so please raise it "
                    "or lower the founder count."
                ),
                detail="founder_count > team_size",
            )
        )

    if (
        founder_count is not None
        and founders_full_time is not None
        and founders_full_time > founder_count
    ):
        findings.append(
            Finding(
                code=FindingCode.MORE_FULL_TIME_THAN_FOUNDERS,
                severity=Severity.CERTAIN,
                fields=("founder_count", "founders_full_time"),
                message=(
                    "You have listed more full-time founders than founders. "
                    "Please check both numbers."
                ),
                detail="founders_full_time > founder_count",
            )
        )

    return findings


def check_entity(
    *,
    founded_year: int | None = None,
    incorporation_year: int | None = None,
) -> list[Finding]:
    """Entity dates that disagree with each other.

    Incorporating *after* starting to trade is legal and common — a sole trader
    who later forms a company — so this is `LIKELY`, not `CERTAIN`, and the
    wording must leave room for the founder to be right. What it catches is the
    mistyped year: 2025 trading / 2019 incorporation is normal; 2019 trading /
    2025 incorporation needs an explanation.
    """
    if (
        founded_year is None
        or incorporation_year is None
        or incorporation_year <= founded_year
    ):
        return []

    return [
        Finding(
            code=FindingCode.INCORPORATED_AFTER_TRADING,
            severity=Severity.LIKELY,
            fields=("founded_year", "incorporation_year"),
            message=(
                "The incorporation year is later than the year you started "
                "trading. That can be right if you traded as a sole trader "
                "before incorporating — if so, no change needed. Otherwise "
                "please check both years."
            ),
            detail="incorporation_year > founded_year",
        )
    ]


# ---------------------------------------------------------------------------
# Contradictions -- semantic, needs the model
# ---------------------------------------------------------------------------


class Contradiction(StructuredOutput):
    """Two submitted claims that cannot both be true."""

    summary: str = Field(
        min_length=1,
        description=(
            "One sentence, addressed to the founder, naming both claims. "
            "Neutral: assume a mistake, never an attempt to mislead."
        ),
    )
    claim: Citation = Field(description="The first claim, with its source.")
    conflicting_claim: Citation = Field(
        description="The claim it cannot be reconciled with, with its source."
    )


class ContradictionReport(StructuredOutput):
    """What one contradiction pass found."""

    contradictions: list[Contradiction] = Field(
        default_factory=list,
        description=(
            "Only genuine conflicts. Two figures that merely differ in "
            "precision, or that cover different periods, are not "
            "contradictions -- omit them."
        ),
    )


SYSTEM_PROMPT: Final = f"""\
You compare a startup's submitted claims and report only those that cannot both
be true.

A contradiction is two statements about the same thing, over the same period,
that conflict. Report it only when you can quote both sides.

These are **not** contradictions:

* Figures covering different periods, or stated at different precision.
* A rounded figure against an exact one.
* A gap -- something stated in one place and simply absent from another.
* A figure you believe is wrong on its own. Arithmetic plausibility is checked
  in code, not here. Your job is disagreement *between* claims.

Write each summary for the founder. Assume a mistake rather than deception: the
overwhelmingly likely cause is an out-of-date deck, not dishonesty, and the tone
must leave room for that.

{UNTRUSTED_RULE}
"""


CONTRADICTION_PROMPT: Final = register(
    PromptVersion(name="consistency_check", version=1, text=SYSTEM_PROMPT)
)
"""The registered, versioned prompt. Its `ref` is recorded on the AuditRun."""


async def find_contradictions(
    client: AiClient,
    *,
    profile_facts: str,
    documents: Sequence[UntrustedContent] = (),
    user_id: str | None = None,
) -> AiResult[ContradictionReport]:
    """Compare submitted claims and report conflicts, each cited on both sides.

    Argument order is the cache ordering, as in `rubric.v1.score` and
    `audit.extraction`: the standing rules go in the cached prefix, this
    startup's facts and documents after the breakpoint, documents last.
    """
    system = cached_system(CONTRADICTION_PROMPT.text)

    facts = profile_facts.strip() or "None supplied."
    body = [
        "Compare the claims below and report only genuine contradictions.",
        "",
        "## Startup Profile as submitted",
        facts,
    ]
    if documents:
        body.extend(["", "## Documents", *(document.text for document in documents)])

    messages: list[MessageParam] = [{"role": "user", "content": "\n".join(body)}]

    return await client.complete(
        tier=ModelTier.AUDIT,
        prompt=CONTRADICTION_PROMPT,
        schema=ContradictionReport,
        system=system,
        messages=messages,
        user_id=user_id,
    )


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------

_PENALTY: Final[dict[Severity, Decimal]] = {
    Severity.CERTAIN: Decimal(25),
    Severity.LIKELY: Decimal(15),
}

_CONTRADICTION_PENALTY: Final = Decimal(20)


def data_integrity_score(
    findings: Sequence[Finding], contradictions: Sequence[Contradiction] = ()
) -> Decimal:
    """How much the submitted data can be trusted, 0-100.

    **Deterministic on purpose.** T2.9 requires the same input to produce the
    same score, which rules out asking a model to judge this. Arithmetic over a
    fixed table is reproducible; a second opinion is not.

    Starts at 100 and deducts per finding. A `CERTAIN` finding costs more than a
    `LIKELY` one because it cannot be a false positive. The floor is 0 -- a
    profile does not go negative, and a score of 0 already means "do not rely on
    any of this".
    """
    score = Decimal(100)
    for finding in findings:
        score -= _PENALTY[finding.severity]
    score -= _CONTRADICTION_PENALTY * len(contradictions)
    return max(Decimal(0), score)
