"""What a figure is compared against, and how well the comparison matched.

Policy for the benchmark knowledge base (T2.3), kept out of the model and the
service so the vocabulary and the fallback order are one short list somebody can
review -- the same reason `intake/fields.py` exists.

**The metric names are `FinancialSummary` field names, deliberately.** A
benchmark keyed by a name `finance.py` does not produce finds nothing, and
"no benchmark stored" is indistinguishable from "benchmark points at a field
that was renamed" -- both return nothing, silently, and the rubric scores
without a comparison it thought it had. A test asserts the correspondence
rather than a comment claiming it.
"""

from decimal import Decimal
from enum import StrEnum
from typing import Final

# Stage is a bounded, shared vocabulary and benchmarks are defined by the PRD as
# keyed by *sector x stage x metric x region*, so this module needs it.
#
# It is imported from `intake` rather than redeclared, which is a **deliberate
# exception** to the module-boundary rule in `ARCHITECTURE.md` section 3: a
# second copy of the same enum would drift the first time a stage is added, and
# a benchmark keyed to a stage the profile cannot hold is worse than an import.
# The tidy fix is promoting `Stage` to `core` alongside `Role` -- noted in
# `TASKS.md` rather than done here, because it touches tested T1.4 code.
from app.modules.intake.fields import Stage

__all__ = [
    "ANY_SECTOR",
    "GLOBAL_REGION",
    "BenchmarkMetric",
    "MatchQuality",
    "Stage",
    "higher_is_better",
    "quartile_position",
]

# Wildcards, stored as ordinary values so a lookup is a plain equality match and
# the fallback chain is four queries rather than one clever one.
ANY_SECTOR: Final[str] = "*"
GLOBAL_REGION: Final[str] = "*"


class BenchmarkMetric(StrEnum):
    """The figures worth comparing against a peer group.

    Every value is a field on `audit.finance.FinancialSummary`.

    **The absolute-currency figures are excluded on purpose.** `net_burn_minor`
    and `annual_run_rate_minor` are amounts, not ratios, and the platform does
    no currency conversion (`finance.py`) -- so a naira burn has no meaningful
    comparison against a benchmark gathered in dollars. Everything here is
    dimensionless or in months, which is exactly why it travels across regions
    unchanged. Adding an amount to this list would mean either an FX feed or a
    silently wrong comparison.
    """

    GROSS_MARGIN_PERCENT = "gross_margin_percent"
    RUNWAY_MONTHS = "runway_months"
    LTV_CAC_RATIO = "ltv_cac_ratio"
    CAC_PAYBACK_MONTHS = "cac_payback_months"
    RUN_RATE_VS_TRAILING_PERCENT = "run_rate_vs_trailing_percent"
    REVENUE_CHANGE_3M_PERCENT = "revenue_change_3m_percent"
    COSTS_CHANGE_3M_PERCENT = "costs_change_3m_percent"


# Which direction is good. A property of the metric, not of any stored row, so
# it is derived rather than a column an admin could set inconsistently across
# two benchmarks for the same metric.
_HIGHER_IS_BETTER: Final[dict[BenchmarkMetric, bool]] = {
    BenchmarkMetric.GROSS_MARGIN_PERCENT: True,
    BenchmarkMetric.RUNWAY_MONTHS: True,
    BenchmarkMetric.LTV_CAC_RATIO: True,
    # The only ones where less is better: months to earn back acquisition cost,
    # and rising operating costs over three months.
    BenchmarkMetric.CAC_PAYBACK_MONTHS: False,
    BenchmarkMetric.RUN_RATE_VS_TRAILING_PERCENT: True,
    BenchmarkMetric.REVENUE_CHANGE_3M_PERCENT: True,
    BenchmarkMetric.COSTS_CHANGE_3M_PERCENT: False,
}


def higher_is_better(metric: BenchmarkMetric) -> bool:
    """Whether a larger value is the better one for this metric.

    The rubric (T2.6) cannot read a quartile band without it: being above p75 is
    excellent for gross margin and poor for CAC payback.
    """
    return _HIGHER_IS_BETTER[metric]


class MatchQuality(StrEnum):
    """How closely a stored benchmark matched what was asked for.

    Returned alongside the value because a comparison against a global,
    any-sector median is a much weaker basis for a verdict than a Nigerian
    fintech one, and the rubric's `provisional` status depends on knowing the
    difference (`CLAUDE.md` section 5). A lookup that returned a number without
    saying how well it matched would produce confident scores off bad
    comparisons.
    """

    EXACT = "exact"
    """Same sector, same region."""

    REGION_FALLBACK = "region_fallback"
    """Same sector, global figures -- the sector is right, the geography is not."""

    SECTOR_FALLBACK = "sector_fallback"
    """Same region, all sectors -- local, but not sector-specific."""

    BROAD = "broad"
    """All sectors, global. Weak; usable as a last resort, not as evidence."""


def quartile_position(
    value: Decimal, p25: Decimal, p50: Decimal, p75: Decimal, metric: BenchmarkMetric
) -> str:
    """Where a value sits in the benchmark band, read in the right direction.

    Returns `top`, `upper_middle`, `lower_middle`, or `bottom` -- named by
    *quality*, not by magnitude, so `top` means good for every metric. For CAC
    payback that is the low end, which is why `higher_is_better` exists.
    """
    if higher_is_better(metric):
        if value >= p75:
            return "top"
        if value >= p50:
            return "upper_middle"
        if value >= p25:
            return "lower_middle"
        return "bottom"
    if value <= p25:
        return "top"
    if value <= p50:
        return "upper_middle"
    if value <= p75:
        return "lower_middle"
    return "bottom"
