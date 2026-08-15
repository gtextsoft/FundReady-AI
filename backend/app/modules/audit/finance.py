"""Deterministic financial computation for the audit engine.

**INVARIANT (DECISIONS.md D9):** every financial figure the platform reports --
margins, burn, runway, CAC/LTV, growth rates, currency normalisation -- is
computed *here, in code*. The LLM interprets these numbers; it never produces
them. Never move a calculation into a prompt, and never accept a computed
figure from model output as ground truth.

Money is handled as integer minor units with an ISO 4217 currency code
(AGENTS.md section 4). Ratios are exact where the inputs allow it.

Three rules this file is built around:

* **"Cannot be computed" is never a number.** Every metric here has a degenerate
  input -- no revenue, no churn, not burning, no acquisition cost -- and each
  returns `None` with a reason rather than a zero. A margin of `0.0` for a
  company with no revenue would be scored by the rubric as a real 0% margin,
  which is exactly the false verdict `CLAUDE.md` section 5 exists to prevent.
  Thin data has to read as thin.
* **`Decimal`, not `float`.** T2.9 requires the same input to produce the same
  score, and accumulated binary rounding across a chain of ratios makes that
  test flaky for reasons that are miserable to find. Decimal is exact and costs
  nothing at this scale.
* **Pure functions over plain integers.** No session, no ORM, no profile
  object. Mapping the Startup Profile's fields onto `FinancialInputs` belongs to
  the pipeline (T2.4/T2.7); keeping it out of here is what makes the golden-set
  harness (T2.9) cheap.

**No currency conversion, deliberately.** Everything is computed in the
profile's own declared currency. It is not needed and would cost accuracy:
benchmarks are region-keyed (T2.3), so a Nigerian startup is compared against
Nigerian benchmarks in naira, and **every ratio that drives scoring is
dimensionless** -- a 62% gross margin and an LTV/CAC of 3.1 mean the same thing
in NGN, GBP, or USD. Conversion would mean an FX feed, an unapproved
dependency, and stale rates on the one set of figures D9 requires to be exact.
The first thing that might genuinely need it is cross-region investor
comparison (T4.3), and that is where the decision belongs.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from typing import Final

# Minor-unit exponents that are not 2. ISO 4217 does not promise two decimal
# places: yen has none, dinars have three. Treating "1000 minor units" as 10.00
# regardless would make the same integer wrong by a factor of 100 in JPY, and a
# benchmark comparison off by 100x looks like a real finding.
_MINOR_UNIT_EXPONENTS: Final[dict[str, int]] = {
    # Zero-decimal
    "BIF": 0,
    "CLP": 0,
    "DJF": 0,
    "GNF": 0,
    "ISK": 0,
    "JPY": 0,
    "KMF": 0,
    "KRW": 0,
    "PYG": 0,
    "RWF": 0,
    "UGX": 0,
    "VND": 0,
    "VUV": 0,
    "XAF": 0,
    "XOF": 0,
    "XPF": 0,
    # Three-decimal
    "BHD": 3,
    "IQD": 3,
    "JOD": 3,
    "KWD": 3,
    "LYD": 3,
    "OMR": 3,
    "TND": 3,
    # Four-decimal
    "CLF": 4,
}
DEFAULT_MINOR_UNIT_EXPONENT: Final[int] = 2

# Where each figure is rounded. Fixed here rather than chosen per caller, so the
# same input produces the same score every time (T2.9).
_PERCENT_PLACES: Final[Decimal] = Decimal("0.01")
_RATIO_PLACES: Final[Decimal] = Decimal("0.01")
_MONTHS_PLACES: Final[Decimal] = Decimal("0.1")
_WHOLE_MINOR_UNITS: Final[Decimal] = Decimal("1")


class Unavailable(StrEnum):
    """Why a figure could not be computed.

    Carried instead of a number so the rubric can say "we do not know" rather
    than score a placeholder. Each value names a *specific* degenerate input,
    because "insufficient data" on its own does not tell a founder what to send.
    """

    MISSING_INPUT = "missing_input"
    NO_REVENUE = "no_revenue"
    NOT_BURNING = "not_burning"
    NO_CHURN = "no_churn"
    NO_ACQUISITION_COST = "no_acquisition_cost"
    NO_CONTRIBUTION = "no_contribution"
    NO_TRAILING_REVENUE = "no_trailing_revenue"
    NO_PRIOR_PERIOD = "no_prior_period"


@dataclass(frozen=True, slots=True)
class Metric:
    """One computed figure, or an explicit statement that it is not knowable.

    `value` and `reason` are mutually exclusive: exactly one is set. Reading
    `value` without checking it against `None` is the mistake this type exists
    to make obvious at the call site.
    """

    value: Decimal | None = None
    reason: Unavailable | None = None

    @property
    def known(self) -> bool:
        return self.value is not None

    @classmethod
    def of(cls, value: Decimal) -> "Metric":
        return cls(value=value)

    @classmethod
    def unknown(cls, reason: Unavailable) -> "Metric":
        return cls(reason=reason)


@dataclass(frozen=True, slots=True)
class FinancialInputs:
    """The raw figures a profile supplies. Every one optional.

    A half-known profile is the normal case, not an error
    (`intake/fields.py`), so nothing here is required and every metric decides
    for itself whether it has what it needs.

    All money is integer **minor units** in `currency`. There is no mixing --
    a profile carries a single currency, which is what makes conversion
    unnecessary rather than merely deferred.
    """

    currency: str = "USD"

    monthly_revenue_minor: int | None = None
    monthly_costs_minor: int | None = None
    cash_on_hand_minor: int | None = None
    cost_of_revenue_minor: int | None = None
    last_12m_revenue_minor: int | None = None
    monthly_revenue_3m_ago_minor: int | None = None
    monthly_costs_3m_ago_minor: int | None = None

    customer_acquisition_cost_minor: int | None = None
    average_revenue_per_customer_minor: int | None = None
    monthly_churn_percent: Decimal | None = None


@dataclass(frozen=True, slots=True)
class FinancialSummary:
    """Everything this module can say about a set of inputs.

    `currency` rides along because the absolute figures are meaningless without
    it. The ratios are dimensionless and comparable across currencies as they
    stand.
    """

    currency: str

    gross_margin_percent: Metric
    net_burn_minor: Metric
    runway_months: Metric
    ltv_minor: Metric
    ltv_cac_ratio: Metric
    cac_payback_months: Metric
    annual_run_rate_minor: Metric
    run_rate_vs_trailing_percent: Metric
    revenue_change_3m_percent: Metric
    costs_change_3m_percent: Metric

    is_profitable: bool | None
    """`True` when the latest month's revenue covered its costs, `None` when
    either is unknown. Not a `Metric` because it is a state, not a
    measurement."""


def minor_unit_exponent(currency: str) -> int:
    """Decimal places for this ISO 4217 code. Two unless it is not."""
    return _MINOR_UNIT_EXPONENTS.get(
        currency.strip().upper(), DEFAULT_MINOR_UNIT_EXPONENT
    )


def to_major_units(amount_minor: int, currency: str) -> Decimal:
    """Minor units to the amount a person would recognise.

    `to_major_units(150000, "USD")` is `1500.00`; the same integer in JPY is
    `150000`. For display, and for comparing against benchmarks quoted in major
    units -- never for arithmetic, which stays in minor units where it is exact.
    """
    exponent = minor_unit_exponent(currency)
    scaled = Decimal(amount_minor) / (Decimal(10) ** exponent)
    return scaled.quantize(Decimal(1).scaleb(-exponent), rounding=ROUND_HALF_UP)


def compute(inputs: FinancialInputs) -> FinancialSummary:
    """Every figure the audit engine gets, from raw inputs alone.

    Deterministic and total: it never raises on thin or degenerate data, it
    reports what it could not work out. Called twice with the same inputs it
    gives identical answers, which is what T2.9 asserts.
    """
    gross_margin = _gross_margin_percent(inputs)
    net_burn = _net_burn_minor(inputs)
    ltv = _ltv_minor(inputs, gross_margin)
    return FinancialSummary(
        currency=inputs.currency.strip().upper(),
        gross_margin_percent=gross_margin,
        net_burn_minor=net_burn,
        runway_months=_runway_months(inputs, net_burn),
        ltv_minor=ltv,
        ltv_cac_ratio=_ltv_cac_ratio(inputs, ltv),
        cac_payback_months=_cac_payback_months(inputs, gross_margin),
        annual_run_rate_minor=_annual_run_rate_minor(inputs),
        run_rate_vs_trailing_percent=_run_rate_vs_trailing_percent(inputs),
        revenue_change_3m_percent=_revenue_change_3m_percent(inputs),
        costs_change_3m_percent=_costs_change_3m_percent(inputs),
        is_profitable=_is_profitable(inputs),
    )


# ---------------------------------------------------------------------------
# The individual figures
# ---------------------------------------------------------------------------


def _gross_margin_percent(inputs: FinancialInputs) -> Metric:
    """`(revenue - cost of revenue) / revenue`, as a percentage.

    Undefined without revenue -- not 0%. A pre-revenue company has no margin,
    which is a different statement from "its margin is nothing", and the rubric
    has to be able to tell them apart.

    Legitimately negative when a company sells below cost. That is a real and
    important finding, so it is reported rather than floored at zero.
    """
    revenue = inputs.monthly_revenue_minor
    cost = inputs.cost_of_revenue_minor
    if revenue is None or cost is None:
        return Metric.unknown(Unavailable.MISSING_INPUT)
    if revenue == 0:
        return Metric.unknown(Unavailable.NO_REVENUE)
    margin = (Decimal(revenue - cost) / Decimal(revenue)) * 100
    return Metric.of(_round(margin, _PERCENT_PLACES))


def _net_burn_minor(inputs: FinancialInputs) -> Metric:
    """Monthly costs minus monthly revenue.

    **Positive means burning cash**, negative means generating it. Stated
    explicitly because both conventions exist in the wild and the rubric reads
    this sign.
    """
    revenue = inputs.monthly_revenue_minor
    costs = inputs.monthly_costs_minor
    if revenue is None or costs is None:
        return Metric.unknown(Unavailable.MISSING_INPUT)
    return Metric.of(Decimal(costs - revenue))


def _runway_months(inputs: FinancialInputs, net_burn: Metric) -> Metric:
    """Cash on hand divided by monthly net burn.

    A company that is not burning has no runway *figure* -- it has no deadline.
    Reporting infinity, or some very large number, would let the rubric score it
    as an exceptionally long runway when the correct reading is that runway is
    the wrong question for a profitable business.
    """
    cash = inputs.cash_on_hand_minor
    if cash is None or net_burn.value is None:
        return Metric.unknown(Unavailable.MISSING_INPUT)
    if net_burn.value <= 0:
        return Metric.unknown(Unavailable.NOT_BURNING)
    return Metric.of(_round(Decimal(cash) / net_burn.value, _MONTHS_PLACES))


def _ltv_minor(inputs: FinancialInputs, gross_margin: Metric) -> Metric:
    """Lifetime value, **margin-adjusted**:
    `(ARPU x gross margin) / monthly churn rate`.

    The margin adjustment is deliberate and worth stating, because the more
    common shortcut -- raw `ARPU / churn` -- materially overstates a low-margin
    business. Revenue a company does not keep is not value. This is the figure
    an investor would compute, so it is the one reported.

    Needs churn. At zero churn the formula diverges, which in practice means the
    input is wrong or the history is too short -- not that customers are worth
    infinitely much.
    """
    arpu = inputs.average_revenue_per_customer_minor
    churn = inputs.monthly_churn_percent
    if arpu is None or churn is None or gross_margin.value is None:
        return Metric.unknown(Unavailable.MISSING_INPUT)
    if churn <= 0:
        return Metric.unknown(Unavailable.NO_CHURN)
    contribution = Decimal(arpu) * (gross_margin.value / 100)
    return Metric.of(_round(contribution / (churn / 100), _WHOLE_MINOR_UNITS))


def _ltv_cac_ratio(inputs: FinancialInputs, ltv: Metric) -> Metric:
    """How many times over a customer repays what it cost to win them.

    The convention investors read as healthy is 3 or above. Undefined when
    acquisition is free -- which is either genuine organic growth or, more
    often, a CAC nobody has measured.
    """
    cac = inputs.customer_acquisition_cost_minor
    if cac is None or ltv.value is None:
        return Metric.unknown(Unavailable.MISSING_INPUT)
    if cac <= 0:
        return Metric.unknown(Unavailable.NO_ACQUISITION_COST)
    return Metric.of(_round(ltv.value / Decimal(cac), _RATIO_PLACES))


def _cac_payback_months(inputs: FinancialInputs, gross_margin: Metric) -> Metric:
    """Months of gross profit per customer needed to repay acquisition cost.

    Undefined when a customer contributes nothing each month: at zero or
    negative contribution the cost is never repaid, and any number here would
    imply that eventually it is.
    """
    cac = inputs.customer_acquisition_cost_minor
    arpu = inputs.average_revenue_per_customer_minor
    if cac is None or arpu is None or gross_margin.value is None:
        return Metric.unknown(Unavailable.MISSING_INPUT)
    contribution = Decimal(arpu) * (gross_margin.value / 100)
    if contribution <= 0:
        return Metric.unknown(Unavailable.NO_CONTRIBUTION)
    return Metric.of(_round(Decimal(cac) / contribution, _MONTHS_PLACES))


def _annual_run_rate_minor(inputs: FinancialInputs) -> Metric:
    """The most recent month, annualised. Not a forecast, not a growth rate.

    Named for exactly what it is: `monthly revenue x 12`. It says what a year
    would look like if nothing changed, which is useful for benchmarking against
    stage and useless as a prediction.
    """
    revenue = inputs.monthly_revenue_minor
    if revenue is None:
        return Metric.unknown(Unavailable.MISSING_INPUT)
    return Metric.of(Decimal(revenue * 12))


def _run_rate_vs_trailing_percent(inputs: FinancialInputs) -> Metric:
    """Current run rate against the trailing twelve months, as a percentage.

    **This is not a growth rate**, and is named so it cannot be mistaken for
    one. A growth rate needs a revenue time series, which the profile does not
    carry -- it holds one month and one trailing total. What this compares is
    where the business is *now* against where it has *been*: positive means the
    latest month annualises above the last year's actual, which is suggestive of
    growth without measuring it.

    A real growth rate over a named period is `revenue_change_3m_percent`.
    """
    revenue = inputs.monthly_revenue_minor
    trailing = inputs.last_12m_revenue_minor
    if revenue is None or trailing is None:
        return Metric.unknown(Unavailable.MISSING_INPUT)
    if trailing <= 0:
        return Metric.unknown(Unavailable.NO_TRAILING_REVENUE)
    change = (Decimal(revenue * 12) - Decimal(trailing)) / Decimal(trailing) * 100
    return Metric.of(_round(change, _PERCENT_PLACES))


def _period_change_percent(current: int | None, prior: int | None) -> Metric:
    """`(current - prior) / prior` as a percentage, or an explicit absence.

    Shared by the revenue and costs three-month trends so the two cannot
    drift. Zero prior is `NO_PRIOR_PERIOD` rather than a wildly large ratio:
    a business that had no revenue three months ago and has some now did not
    grow by infinity, it started.
    """
    if current is None or prior is None:
        return Metric.unknown(Unavailable.MISSING_INPUT)
    if prior <= 0:
        return Metric.unknown(Unavailable.NO_PRIOR_PERIOD)
    change = (Decimal(current) - Decimal(prior)) / Decimal(prior) * 100
    return Metric.of(_round(change, _PERCENT_PLACES))


def _revenue_change_3m_percent(inputs: FinancialInputs) -> Metric:
    """Latest month's revenue against revenue three months ago, as a percentage.

    Positive means growing. This is the figure that lets the rubric tell a
    business growing 20% a month from one shrinking at the same rate — which
    `run_rate_vs_trailing_percent` cannot, because it only has one frozen month
    and a trailing total.
    """
    return _period_change_percent(
        inputs.monthly_revenue_minor, inputs.monthly_revenue_3m_ago_minor
    )


def _costs_change_3m_percent(inputs: FinancialInputs) -> Metric:
    """Latest month's costs against costs three months ago, as a percentage.

    Positive means costs are rising. The direction the rubric wants depends on
    whether revenue rose faster; the figure itself is just the trend.
    """
    return _period_change_percent(
        inputs.monthly_costs_minor, inputs.monthly_costs_3m_ago_minor
    )


def _is_profitable(inputs: FinancialInputs) -> bool | None:
    """Whether the most recent month covered its own costs."""
    revenue = inputs.monthly_revenue_minor
    costs = inputs.monthly_costs_minor
    if revenue is None or costs is None:
        return None
    return revenue >= costs


def _round(value: Decimal, places: Decimal) -> Decimal:
    """Round half-up to a fixed precision.

    Banker's rounding -- Decimal's default -- sends `2.5` and `3.5` in different
    directions. That is correct for summing ledgers and surprising in a report a
    founder reads, so figures here round the way people expect. Fixed precision
    per figure is what keeps the same input producing the same score (T2.9).
    """
    try:
        return value.quantize(places, rounding=ROUND_HALF_UP)
    except InvalidOperation:  # pragma: no cover - guards absurd magnitudes only
        return value


__all__ = [
    "DEFAULT_MINOR_UNIT_EXPONENT",
    "FinancialInputs",
    "FinancialSummary",
    "Metric",
    "Unavailable",
    "compute",
    "minor_unit_exponent",
    "to_major_units",
]
