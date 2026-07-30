"""The benchmark metric vocabulary is tied to what `finance.py` produces (T2.3).

This is the test the design hangs on. A benchmark keyed by a name
`FinancialSummary` does not carry finds nothing at lookup -- and "no benchmark
stored" and "benchmark points at a field that was renamed" are *the same
answer*: `None`, silently, with the rubric scoring on without the comparison it
believed it had.

A comment claiming the names line up cannot fail. This can.
"""

from dataclasses import fields as dataclass_fields
from decimal import Decimal

import pytest

from app.modules.audit.benchmarks import (
    ANY_SECTOR,
    GLOBAL_REGION,
    BenchmarkMetric,
    MatchQuality,
    higher_is_better,
    quartile_position,
)
from app.modules.audit.finance import FinancialSummary

SUMMARY_FIELDS = {field.name for field in dataclass_fields(FinancialSummary)}


class TestTheVocabularyMatchesFinance:
    @pytest.mark.parametrize("metric", list(BenchmarkMetric))
    def test_every_metric_is_a_financial_summary_field(
        self, metric: BenchmarkMetric
    ) -> None:
        assert metric.value in SUMMARY_FIELDS, (
            f"{metric.value} is not produced by finance.py -- a benchmark keyed "
            "to it can never be compared against anything"
        )

    def test_absolute_currency_figures_are_excluded(self) -> None:
        """The platform does no FX conversion, so a naira burn has no
        meaningful comparison against a benchmark gathered in dollars. Only
        dimensionless ratios and month counts travel across regions."""
        values = {metric.value for metric in BenchmarkMetric}

        assert "net_burn_minor" not in values
        assert "annual_run_rate_minor" not in values

    def test_the_excluded_ones_really_are_summary_fields(self) -> None:
        """Proves the exclusion is a decision, not an oversight -- both exist
        on FinancialSummary and were left out deliberately."""
        assert "net_burn_minor" in SUMMARY_FIELDS
        assert "annual_run_rate_minor" in SUMMARY_FIELDS

    def test_every_metric_has_a_direction(self) -> None:
        """Without it the rubric cannot read a quartile band."""
        for metric in BenchmarkMetric:
            assert isinstance(higher_is_better(metric), bool)


class TestDirection:
    def test_more_margin_is_better(self) -> None:
        assert higher_is_better(BenchmarkMetric.GROSS_MARGIN_PERCENT) is True

    def test_more_runway_is_better(self) -> None:
        assert higher_is_better(BenchmarkMetric.RUNWAY_MONTHS) is True

    def test_faster_payback_is_better(self) -> None:
        """The one metric where less is more."""
        assert higher_is_better(BenchmarkMetric.CAC_PAYBACK_MONTHS) is False


class TestQuartilePosition:
    """Positions are named by *quality*, so `top` means good for every metric."""

    def test_a_high_margin_is_top(self) -> None:
        position = quartile_position(
            Decimal("80"),
            Decimal("20"),
            Decimal("40"),
            Decimal("60"),
            BenchmarkMetric.GROSS_MARGIN_PERCENT,
        )

        assert position == "top"

    def test_a_low_margin_is_bottom(self) -> None:
        position = quartile_position(
            Decimal("5"),
            Decimal("20"),
            Decimal("40"),
            Decimal("60"),
            BenchmarkMetric.GROSS_MARGIN_PERCENT,
        )

        assert position == "bottom"

    def test_a_fast_payback_is_top_even_though_it_is_the_low_end(self) -> None:
        """The direction flip. Scoring this like margin would tell a founder
        with excellent payback that they are bottom-quartile."""
        position = quartile_position(
            Decimal("2"),
            Decimal("6"),
            Decimal("12"),
            Decimal("18"),
            BenchmarkMetric.CAC_PAYBACK_MONTHS,
        )

        assert position == "top"

    def test_a_slow_payback_is_bottom(self) -> None:
        position = quartile_position(
            Decimal("30"),
            Decimal("6"),
            Decimal("12"),
            Decimal("18"),
            BenchmarkMetric.CAC_PAYBACK_MONTHS,
        )

        assert position == "bottom"

    def test_the_boundaries_belong_to_the_better_band(self) -> None:
        """Exactly p75 on a higher-is-better metric counts as top."""
        position = quartile_position(
            Decimal("60"),
            Decimal("20"),
            Decimal("40"),
            Decimal("60"),
            BenchmarkMetric.GROSS_MARGIN_PERCENT,
        )

        assert position == "top"


class TestWildcards:
    def test_they_are_distinct_from_any_real_value(self) -> None:
        """`*` is not a sector anyone would type and not an ISO region code."""
        assert ANY_SECTOR == "*"
        assert GLOBAL_REGION == "*"

    def test_the_region_wildcard_fits_the_column(self) -> None:
        """`region` is String(2) to match ISO alpha-2."""
        assert len(GLOBAL_REGION) <= 2


class TestMatchQuality:
    def test_all_four_rungs_exist(self) -> None:
        assert {quality.value for quality in MatchQuality} == {
            "exact",
            "region_fallback",
            "sector_fallback",
            "broad",
        }
