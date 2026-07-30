"""Profile field values are checked against the kind they declare (T2.2a).

`FieldKind` was a contract enforced by nothing: `PERCENT` carried the comment
"0-100" and `150` stored fine, `MONEY_MINOR` said integer minor units and
`45000.50` stored fine. Every one of these feeds `finance.py`, whose output a
founder acts on and an investor is shown, so a wrong type is a wrong figure
rather than a wrong pixel.

**The limit of this layer is pinned here too.** A percentage submitted as a
fraction is not caught and cannot be: `0.02` meaning 2% is indistinguishable
from `0.02` meaning 0.02%, since a genuinely low-churn business exists. That
ambiguity produces an LTV a hundred times too high, and closing it needs
cross-field plausibility -- the consistency stage (T2.5), which can weigh churn
against customer counts and revenue instead of judging one number alone.
"""

import pytest
from pydantic import ValidationError

from app.modules.intake.fields import FIELDS_BY_NAME, value_error
from app.modules.intake.schemas import StartupProfileCreate


def field(name: str, value: object) -> dict[str, object]:
    return {"fields": {name: {"value": value, "source": "founder"}}}


class TestTheChurnCase:
    """Range checking, and the thing it provably cannot do.

    A percentage submitted as a fraction is **not** caught here and cannot be:
    `0.02` meaning 2% is indistinguishable from `0.02` meaning 0.02%, because a
    genuinely low-churn business exists and refusing it would be wrong. That
    ambiguity yields an LTV a hundred times too high and belongs to the
    consistency stage (T2.5), which can weigh churn against customer counts and
    revenue instead of judging one number alone.
    """

    def test_a_fraction_is_accepted_and_that_is_a_known_gap(self) -> None:
        """Pinned so nobody later believes this layer closed it."""
        profile = StartupProfileCreate(**field("monthly_churn_percent", 0.02))  # type: ignore[arg-type]

        assert profile.fields is not None

    def test_the_same_number_as_a_percentage_is_fine(self) -> None:
        """2 meaning 2% is what the field asks for."""
        profile = StartupProfileCreate(**field("monthly_churn_percent", 2))  # type: ignore[arg-type]

        assert profile.fields is not None

    def test_a_fractional_percentage_is_still_allowed(self) -> None:
        """1.5% is a real churn rate, so decimals are not refused outright --
        which is exactly why the fraction case above cannot be caught here."""
        profile = StartupProfileCreate(**field("monthly_churn_percent", 1.5))  # type: ignore[arg-type]

        assert profile.fields is not None

    def test_over_one_hundred_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            StartupProfileCreate(**field("monthly_churn_percent", 150))  # type: ignore[arg-type]

    def test_negative_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            StartupProfileCreate(**field("monthly_churn_percent", -5))  # type: ignore[arg-type]


class TestMoney:
    def test_an_integer_in_minor_units_is_accepted(self) -> None:
        assert value_error(FIELDS_BY_NAME["monthly_revenue_minor"], 4_500_000) is None

    def test_a_decimal_amount_is_refused(self) -> None:
        """45000.50 means someone sent major units. Minor units are integers."""
        problem = value_error(FIELDS_BY_NAME["monthly_revenue_minor"], 45000.50)

        assert problem is not None
        assert "minor units" in problem

    def test_negative_money_is_refused(self) -> None:
        assert value_error(FIELDS_BY_NAME["cash_on_hand_minor"], -1) is not None

    def test_text_where_money_belongs_is_refused(self) -> None:
        assert value_error(FIELDS_BY_NAME["monthly_revenue_minor"], "45000") is not None


class TestCounts:
    def test_a_whole_number_is_accepted(self) -> None:
        assert value_error(FIELDS_BY_NAME["team_size"], 12) is None

    def test_negative_headcount_is_refused(self) -> None:
        assert value_error(FIELDS_BY_NAME["team_size"], -3) is not None

    def test_a_fractional_headcount_is_refused(self) -> None:
        assert value_error(FIELDS_BY_NAME["team_size"], 2.5) is not None


class TestBooleansAreNotNumbers:
    """`isinstance(True, int)` is True in Python. Without an explicit guard,
    `"team_size": true` stores a team of one."""

    def test_true_is_not_a_headcount(self) -> None:
        assert value_error(FIELDS_BY_NAME["team_size"], True) is not None

    def test_true_is_not_an_amount(self) -> None:
        assert value_error(FIELDS_BY_NAME["monthly_revenue_minor"], True) is not None

    def test_true_is_not_a_percentage(self) -> None:
        assert value_error(FIELDS_BY_NAME["monthly_churn_percent"], True) is not None

    def test_a_boolean_field_does_want_a_boolean(self) -> None:
        assert value_error(FIELDS_BY_NAME["ip_owned"], True) is None

    def test_a_number_is_not_a_boolean(self) -> None:
        assert value_error(FIELDS_BY_NAME["ip_owned"], 1) is not None


class TestYears:
    def test_a_plausible_year_is_accepted(self) -> None:
        assert value_error(FIELDS_BY_NAME["founded_year"], 2021) is None

    @pytest.mark.parametrize("year", [12, 202, 99999, -2020])
    def test_a_typo_is_refused(self, year: int) -> None:
        assert value_error(FIELDS_BY_NAME["founded_year"], year) is not None


class TestText:
    def test_text_is_accepted(self) -> None:
        assert value_error(FIELDS_BY_NAME["description"], "Same-day parcels") is None

    def test_a_number_where_text_belongs_is_refused(self) -> None:
        assert value_error(FIELDS_BY_NAME["description"], 42) is not None


class TestEmptyValues:
    """A field present but empty is a placeholder, and `missing_fields` already
    reports it as absent -- so it must not also be a validation error."""

    def test_none_is_always_allowed(self) -> None:
        for spec in FIELDS_BY_NAME.values():
            assert value_error(spec, None) is None

    def test_a_null_value_survives_the_schema(self) -> None:
        profile = StartupProfileCreate(**field("monthly_churn_percent", None))  # type: ignore[arg-type]

        assert profile.fields is not None


class TestTheErrorIsUseful:
    def test_it_names_the_offending_field(self) -> None:
        """A founder filling a long form needs to know which one."""
        with pytest.raises(ValidationError) as refusal:
            StartupProfileCreate(**field("team_size", -1))  # type: ignore[arg-type]

        assert "team_size" in str(refusal.value)

    def test_several_problems_are_reported_together(self) -> None:
        """Not one per round trip."""
        payload = {
            "fields": {
                "team_size": {"value": -1, "source": "founder"},
                "founded_year": {"value": 12, "source": "founder"},
            }
        }

        with pytest.raises(ValidationError) as refusal:
            StartupProfileCreate(**payload)  # type: ignore[arg-type]

        message = str(refusal.value)
        assert "team_size" in message
        assert "founded_year" in message


class TestEveryFieldIsCovered:
    def test_no_kind_is_left_unchecked(self) -> None:
        """A new FieldKind added without a rule here would validate nothing."""
        for spec in FIELDS_BY_NAME.values():
            # A string is wrong for every kind except TEXT, so this proves each
            # spec's kind reaches a real branch rather than falling through.
            problem = value_error(spec, "definitely-not-valid-for-most-kinds")
            assert (problem is None) == (spec.kind.value == "text"), spec.name
