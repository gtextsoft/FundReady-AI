"""Deterministic financial computation (T2.2).

`DECISIONS.md` **D9** makes this file's correctness an invariant: the LLM
interprets these numbers and never produces them, so anything wrong here is
wrong in a report a founder acts on and an investor is shown.

The bulk of what is asserted is not the happy arithmetic -- that part is a
division -- but the **degenerate inputs**. A company with no revenue, no churn,
or no burn must come back as *unknown with a reason*, never as a zero, because
`CLAUDE.md` section 5 forbids a false verdict on thin data and a `0.0` margin
would be scored as a real one.

No database, no fixtures, no LLM: plain integers in, figures out.
"""

from decimal import Decimal

import pytest

from app.modules.audit.finance import (
    FinancialInputs,
    Metric,
    Unavailable,
    compute,
    minor_unit_exponent,
    to_major_units,
)
from tests.conftest import REPO_ROOT

# A healthy-looking SaaS business, in minor units. GBP 50,000 monthly revenue,
# GBP 15,000 cost of revenue -> 70% gross margin.
HEALTHY = FinancialInputs(
    currency="GBP",
    monthly_revenue_minor=5_000_000,
    monthly_costs_minor=8_000_000,
    cash_on_hand_minor=48_000_000,
    cost_of_revenue_minor=1_500_000,
    last_12m_revenue_minor=48_000_000,
    customer_acquisition_cost_minor=90_000,
    average_revenue_per_customer_minor=25_000,
    monthly_churn_percent=Decimal("2"),
)


class TestGrossMargin:
    def test_it_is_revenue_less_cost_of_revenue(self) -> None:
        result = compute(HEALTHY)

        assert result.gross_margin_percent.value == Decimal("70.00")

    def test_selling_below_cost_reports_a_negative_margin(self) -> None:
        """A real and important finding, so it is not floored at zero."""
        inputs = FinancialInputs(
            monthly_revenue_minor=100_000, cost_of_revenue_minor=150_000
        )

        assert compute(inputs).gross_margin_percent.value == Decimal("-50.00")

    def test_no_revenue_is_unknown_not_zero(self) -> None:
        """A pre-revenue company has no margin. That is not a 0% margin."""
        inputs = FinancialInputs(monthly_revenue_minor=0, cost_of_revenue_minor=0)

        margin = compute(inputs).gross_margin_percent

        assert margin.value is None
        assert margin.reason is Unavailable.NO_REVENUE

    def test_a_missing_cost_of_revenue_is_unknown(self) -> None:
        inputs = FinancialInputs(monthly_revenue_minor=100_000)

        margin = compute(inputs).gross_margin_percent

        assert margin.value is None
        assert margin.reason is Unavailable.MISSING_INPUT


class TestNetBurnAndRunway:
    def test_burn_is_positive_when_burning(self) -> None:
        """The sign convention the rubric reads. Costs 80k, revenue 50k."""
        assert compute(HEALTHY).net_burn_minor.value == Decimal("3000000")

    def test_burn_is_negative_when_generating_cash(self) -> None:
        inputs = FinancialInputs(
            monthly_revenue_minor=900_000, monthly_costs_minor=400_000
        )

        assert compute(inputs).net_burn_minor.value == Decimal("-500000")

    def test_runway_is_cash_over_burn(self) -> None:
        """480,000 cash / 30,000 monthly burn = 16 months."""
        assert compute(HEALTHY).runway_months.value == Decimal("16.0")

    def test_a_profitable_company_has_no_runway_figure(self) -> None:
        """Not infinity, and not a very large number the rubric would score as
        an exceptionally long runway. Runway is the wrong question here."""
        inputs = FinancialInputs(
            monthly_revenue_minor=900_000,
            monthly_costs_minor=400_000,
            cash_on_hand_minor=10_000_000,
        )

        runway = compute(inputs).runway_months

        assert runway.value is None
        assert runway.reason is Unavailable.NOT_BURNING

    def test_breaking_exactly_even_is_also_not_burning(self) -> None:
        inputs = FinancialInputs(
            monthly_revenue_minor=500_000,
            monthly_costs_minor=500_000,
            cash_on_hand_minor=1_000_000,
        )

        assert compute(inputs).runway_months.reason is Unavailable.NOT_BURNING

    def test_missing_cash_is_unknown(self) -> None:
        inputs = FinancialInputs(
            monthly_revenue_minor=100_000, monthly_costs_minor=400_000
        )

        assert compute(inputs).runway_months.reason is Unavailable.MISSING_INPUT


class TestLifetimeValue:
    def test_it_is_margin_adjusted(self) -> None:
        """(ARPU 250 x 70% margin) / 2% churn = 8,750 major = 875,000 minor.

        Deliberately not the raw `ARPU / churn` shortcut, which would give
        12,500 -- revenue the company does not keep is not value.
        """
        assert compute(HEALTHY).ltv_minor.value == Decimal("875000")

    def test_zero_churn_is_unknown_not_infinite(self) -> None:
        """The formula diverges. In practice that means the input is wrong."""
        inputs = FinancialInputs(
            monthly_revenue_minor=5_000_000,
            cost_of_revenue_minor=1_500_000,
            average_revenue_per_customer_minor=25_000,
            monthly_churn_percent=Decimal("0"),
        )

        ltv = compute(inputs).ltv_minor

        assert ltv.value is None
        assert ltv.reason is Unavailable.NO_CHURN

    def test_it_needs_a_margin_to_adjust_by(self) -> None:
        inputs = FinancialInputs(
            average_revenue_per_customer_minor=25_000,
            monthly_churn_percent=Decimal("2"),
        )

        assert compute(inputs).ltv_minor.reason is Unavailable.MISSING_INPUT


class TestLtvToCac:
    def test_it_is_lifetime_value_over_acquisition_cost(self) -> None:
        """875,000 / 90,000 = 9.72 -- comfortably above the 3 investors read."""
        assert compute(HEALTHY).ltv_cac_ratio.value == Decimal("9.72")

    def test_free_acquisition_is_unknown(self) -> None:
        """Either genuine organic growth or a CAC nobody measured."""
        inputs = FinancialInputs(
            monthly_revenue_minor=5_000_000,
            cost_of_revenue_minor=1_500_000,
            average_revenue_per_customer_minor=25_000,
            monthly_churn_percent=Decimal("2"),
            customer_acquisition_cost_minor=0,
        )

        ratio = compute(inputs).ltv_cac_ratio

        assert ratio.value is None
        assert ratio.reason is Unavailable.NO_ACQUISITION_COST


class TestCacPayback:
    def test_it_is_cac_over_monthly_contribution(self) -> None:
        """CAC 900 / (ARPU 250 x 70%) = 900 / 175 = 5.1 months."""
        assert compute(HEALTHY).cac_payback_months.value == Decimal("5.1")

    def test_no_contribution_is_unknown(self) -> None:
        """At a negative margin the cost is never repaid; any number would
        imply that eventually it is."""
        inputs = FinancialInputs(
            monthly_revenue_minor=100_000,
            cost_of_revenue_minor=150_000,
            average_revenue_per_customer_minor=25_000,
            customer_acquisition_cost_minor=90_000,
        )

        payback = compute(inputs).cac_payback_months

        assert payback.value is None
        assert payback.reason is Unavailable.NO_CONTRIBUTION


class TestRunRate:
    def test_the_run_rate_is_the_month_annualised(self) -> None:
        assert compute(HEALTHY).annual_run_rate_minor.value == Decimal("60000000")

    def test_it_is_compared_against_the_trailing_year(self) -> None:
        """600,000 run rate against 480,000 actual = 25% above."""
        assert compute(HEALTHY).run_rate_vs_trailing_percent.value == Decimal("25.00")

    def test_a_shrinking_business_reports_negative(self) -> None:
        inputs = FinancialInputs(
            monthly_revenue_minor=3_000_000, last_12m_revenue_minor=48_000_000
        )

        assert compute(inputs).run_rate_vs_trailing_percent.value == Decimal("-25.00")

    def test_no_trailing_revenue_is_unknown(self) -> None:
        inputs = FinancialInputs(
            monthly_revenue_minor=3_000_000, last_12m_revenue_minor=0
        )

        result = compute(inputs).run_rate_vs_trailing_percent

        assert result.value is None
        assert result.reason is Unavailable.NO_TRAILING_REVENUE


class TestProfitability:
    def test_covering_costs_is_profitable(self) -> None:
        inputs = FinancialInputs(
            monthly_revenue_minor=900_000, monthly_costs_minor=400_000
        )

        assert compute(inputs).is_profitable is True

    def test_burning_is_not(self) -> None:
        assert compute(HEALTHY).is_profitable is False

    def test_unknown_when_either_side_is_missing(self) -> None:
        """`None`, not `False`. We do not know, which is not the same as no."""
        assert compute(FinancialInputs(monthly_revenue_minor=100)).is_profitable is None


class TestAnEmptyProfile:
    """The normal starting state: a founder who has filled in nothing."""

    def test_nothing_is_computed_and_nothing_raises(self) -> None:
        result = compute(FinancialInputs())

        assert result.is_profitable is None
        for metric in (
            result.gross_margin_percent,
            result.net_burn_minor,
            result.runway_months,
            result.ltv_minor,
            result.ltv_cac_ratio,
            result.cac_payback_months,
            result.annual_run_rate_minor,
            result.run_rate_vs_trailing_percent,
        ):
            assert metric.value is None
            assert metric.reason is Unavailable.MISSING_INPUT

    def test_no_metric_is_silently_zero(self) -> None:
        """The whole point: absent must not read as measured-and-nil."""
        result = compute(FinancialInputs())

        assert not any(
            metric.value == 0
            for metric in (result.gross_margin_percent, result.runway_months)
        )


class TestDeterminism:
    """T2.9 asserts the same input produces the same score. That starts here."""

    def test_the_same_inputs_give_identical_figures(self) -> None:
        assert compute(HEALTHY) == compute(HEALTHY)

    def test_repeated_calls_do_not_drift(self) -> None:
        values = {compute(HEALTHY).ltv_cac_ratio.value for _ in range(50)}

        assert len(values) == 1

    def test_figures_are_decimal_not_float(self) -> None:
        """Float accumulation across chained ratios makes determinism flaky."""
        result = compute(HEALTHY)

        assert isinstance(result.gross_margin_percent.value, Decimal)
        assert isinstance(result.ltv_cac_ratio.value, Decimal)

    def test_a_third_of_a_margin_rounds_predictably(self) -> None:
        """Repeating decimals must land on a stated precision, not wander."""
        inputs = FinancialInputs(
            monthly_revenue_minor=300_000, cost_of_revenue_minor=100_000
        )

        assert compute(inputs).gross_margin_percent.value == Decimal("66.67")


class TestCurrency:
    def test_most_currencies_have_two_decimal_places(self) -> None:
        assert minor_unit_exponent("USD") == 2
        assert minor_unit_exponent("NGN") == 2
        assert minor_unit_exponent("GBP") == 2

    @pytest.mark.parametrize("currency", ["JPY", "KRW", "XOF", "VND"])
    def test_some_have_none(self, currency: str) -> None:
        assert minor_unit_exponent(currency) == 0

    @pytest.mark.parametrize("currency", ["KWD", "BHD", "TND", "JOD"])
    def test_some_have_three(self, currency: str) -> None:
        assert minor_unit_exponent(currency) == 3

    def test_an_unknown_code_falls_back_to_two(self) -> None:
        assert minor_unit_exponent("ZZZ") == 2

    def test_the_code_is_normalised(self) -> None:
        assert minor_unit_exponent("  jpy  ") == 0

    def test_the_same_integer_means_different_amounts(self) -> None:
        """The reason the exponent table exists: 150000 minor units is 1500
        dollars but 150000 yen. Getting this wrong is a 100x benchmark error."""
        assert to_major_units(150_000, "USD") == Decimal("1500.00")
        assert to_major_units(150_000, "JPY") == Decimal("150000")
        assert to_major_units(150_000, "KWD") == Decimal("150.000")

    def test_the_summary_carries_its_currency(self) -> None:
        """Absolute figures are meaningless without it."""
        assert compute(HEALTHY).currency == "GBP"

    def test_the_currency_is_normalised_to_upper_case(self) -> None:
        assert compute(FinancialInputs(currency="ngn")).currency == "NGN"

    def test_ratios_are_currency_free(self) -> None:
        """No conversion is needed because the figures that drive scoring are
        dimensionless -- 70% is 70% in naira or sterling."""
        naira = compute(
            FinancialInputs(
                currency="NGN",
                monthly_revenue_minor=5_000_000,
                cost_of_revenue_minor=1_500_000,
            )
        )
        sterling = compute(
            FinancialInputs(
                currency="GBP",
                monthly_revenue_minor=5_000_000,
                cost_of_revenue_minor=1_500_000,
            )
        )

        assert naira.gross_margin_percent == sterling.gross_margin_percent


class TestMetric:
    def test_a_known_metric_reports_known(self) -> None:
        assert Metric.of(Decimal("1")).known is True

    def test_an_unknown_one_does_not(self) -> None:
        assert Metric.unknown(Unavailable.NO_REVENUE).known is False

    def test_value_and_reason_never_both_appear(self) -> None:
        result = compute(HEALTHY)

        for metric in (result.gross_margin_percent, result.runway_months):
            assert (metric.value is None) != (metric.reason is None)


class TestTheInvariantIsStructural:
    """D9 says the model never produces these numbers. A docstring saying so is
    weaker than an import that cannot exist."""

    def test_finance_does_not_import_the_ai_package(self) -> None:
        source = (REPO_ROOT / "app" / "modules" / "audit" / "finance.py").read_text(
            encoding="utf-8"
        )

        assert "app.ai" not in source
        assert "import anthropic" not in source
