"""T2.5: does the submitted data agree with itself?

Two things are being defended here, and the second is the harder one.

**A planted error is caught** -- the task's done-when.

**A correct profile is left alone.** Thresholds are loose on purpose, so the
false-positive tests are not padding: telling a founder their revenue looks
wrong when it is right costs more trust than missing one subtle error, and a
consistency checker nobody believes is worse than none. Every check therefore
has a paired "this is fine" case.

The `log_context` tests enforce `CLAUDE.md` section 4: the founder may see their
own figures, a shared log may not.
"""

from decimal import Decimal

import pytest

from app.modules.audit.consistency import (
    Contradiction,
    FindingCode,
    Severity,
    check_entity,
    check_scale,
    check_team,
    data_integrity_score,
)
from app.modules.audit.finance import FinancialInputs

# 1 NGN = 100 kobo, so a naira figure entered into a kobo field is 100x light.
NAIRA = 100


def _codes(findings: object) -> set[str]:
    return {f.code.value for f in findings}  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Planted errors are caught -- the done-when
# ---------------------------------------------------------------------------


def test_revenue_entered_in_major_units_is_caught() -> None:
    """The classic: whole naira typed into a field that expects kobo."""
    inputs = FinancialInputs(
        currency="NGN",
        monthly_revenue_minor=41_000 * NAIRA,
        last_12m_revenue_minor=4_100,  # naira, should have been kobo
    )

    assert FindingCode.REVENUE_VS_ANNUAL.value in _codes(check_scale(inputs))


def test_revenue_that_customers_cannot_explain_is_caught() -> None:
    inputs = FinancialInputs(
        currency="NGN",
        monthly_revenue_minor=4_100_000 * NAIRA,
        average_revenue_per_customer_minor=1_200 * NAIRA,
    )

    findings = check_scale(inputs, active_customers=34)

    assert FindingCode.REVENUE_VS_CUSTOMERS.value in _codes(findings)


def test_a_fraction_entered_as_a_percent_is_caught() -> None:
    """`0.02` meaning 2%. Yields an LTV 100x too high if it survives (T2.2a)."""
    inputs = FinancialInputs(monthly_churn_percent=Decimal("0.02"))

    findings = check_scale(inputs, active_customers=34)

    assert FindingCode.CHURN_IMPLAUSIBLY_LOW.value in _codes(findings)


def test_more_founders_than_staff_is_certain_not_a_guess() -> None:
    findings = check_team(team_size=3, founder_count=4)

    assert findings[0].code is FindingCode.MORE_FOUNDERS_THAN_TEAM
    assert findings[0].severity is Severity.CERTAIN


def test_incorporating_after_trading_is_flagged_as_likely() -> None:
    """Likely, not certain: sole traders who later incorporate are common."""
    findings = check_entity(founded_year=2019, incorporation_year=2023)

    assert findings[0].code is FindingCode.INCORPORATED_AFTER_TRADING
    assert findings[0].severity is Severity.LIKELY


def test_incorporating_in_the_same_year_as_trading_is_fine() -> None:
    assert check_entity(founded_year=2020, incorporation_year=2020) == []


def test_trading_after_incorporation_is_fine() -> None:
    """The normal case: form the company, then start trading."""
    assert check_entity(founded_year=2021, incorporation_year=2020) == []


def test_a_half_known_entity_is_not_flagged() -> None:
    assert check_entity(founded_year=2019) == []
    assert check_entity(incorporation_year=2023) == []


# ---------------------------------------------------------------------------
# Correct data is left alone
# ---------------------------------------------------------------------------


def test_a_consistent_profile_produces_no_findings() -> None:
    inputs = FinancialInputs(
        currency="NGN",
        monthly_revenue_minor=4_100_000 * NAIRA,
        last_12m_revenue_minor=45_000_000 * NAIRA,
        average_revenue_per_customer_minor=120_000 * NAIRA,
        monthly_churn_percent=Decimal("2.5"),
        cost_of_revenue_minor=1_200_000 * NAIRA,
    )

    assert check_scale(inputs, active_customers=34) == []


def test_a_genuine_tiny_churn_at_scale_is_not_flagged() -> None:
    """0.02% of 50,000 customers is ten people a month -- a real, measured number.

    This is why the check is cross-field. On range alone it is identical to the
    mistyped 2% above, and flagging it would tell a large, healthy business that
    its best metric looks like a mistake.
    """
    inputs = FinancialInputs(monthly_churn_percent=Decimal("0.02"))

    findings = check_scale(inputs, active_customers=50_000)

    assert FindingCode.CHURN_IMPLAUSIBLY_LOW.value not in _codes(findings)


def test_a_merely_surprising_discrepancy_is_not_reported() -> None:
    """3x is not flagged. Only order-of-magnitude errors are.

    A business whose trailing year does not equal twelve times last month is
    normal -- it grew, or it shrank.
    """
    inputs = FinancialInputs(
        monthly_revenue_minor=1_000_000,
        last_12m_revenue_minor=4_000_000,  # 3x off implied 12m
    )

    assert check_scale(inputs) == []


def test_missing_figures_are_a_gap_not_a_contradiction() -> None:
    """A half-known profile is the normal case, never an error."""
    assert check_scale(FinancialInputs(monthly_revenue_minor=500_000)) == []
    assert check_team(team_size=4) == []


def test_zero_revenue_is_pre_revenue_not_an_inconsistency() -> None:
    """A pre-revenue startup must not be told its figures look wrong."""
    inputs = FinancialInputs(monthly_revenue_minor=0, last_12m_revenue_minor=0)

    assert check_scale(inputs) == []


# ---------------------------------------------------------------------------
# Messages: two audiences
# ---------------------------------------------------------------------------


def test_the_founder_message_says_what_to_do_about_it() -> None:
    inputs = FinancialInputs(
        monthly_revenue_minor=41_000 * NAIRA, last_12m_revenue_minor=4_100
    )

    finding = check_scale(inputs)[0]

    assert "check both figures" in finding.message.lower()
    assert finding.message[0].isupper() and finding.message.endswith(".")


def test_the_founder_message_never_accuses() -> None:
    """The overwhelmingly likely cause is a mistyped unit, not dishonesty.

    A tool that implies a founder is lying about their own numbers will not be
    used twice.
    """
    accusatory = ("lying", "false", "fraud", "dishonest", "misleading", "incorrect")
    inputs = FinancialInputs(
        monthly_revenue_minor=41_000 * NAIRA,
        last_12m_revenue_minor=4_100,
        monthly_churn_percent=Decimal("0.02"),
    )

    findings = [
        *check_scale(inputs, active_customers=10),
        *check_team(team_size=2, founder_count=5),
    ]
    assert findings

    for finding in findings:
        lowered = finding.message.lower()
        assert not any(word in lowered for word in accusatory), finding.code


def test_the_engineer_detail_names_the_comparison_that_fired() -> None:
    """So a support conversation does not require re-deriving the check."""
    inputs = FinancialInputs(
        monthly_revenue_minor=41_000 * NAIRA, last_12m_revenue_minor=4_100
    )

    finding = check_scale(inputs)[0]

    assert "monthly_revenue_minor" in finding.detail
    assert "10x" in finding.detail


def test_log_context_carries_no_figures() -> None:
    """`CLAUDE.md` §4: financial values never reach a log.

    The founder sees their own numbers; a log read by operators and shipped to
    an aggregator is a different audience entirely.
    """
    inputs = FinancialInputs(
        monthly_revenue_minor=4_100_000, last_12m_revenue_minor=4_100
    )

    for finding in check_scale(inputs):
        context = finding.log_context()
        assert set(context) == {"code", "severity", "fields"}
        rendered = str(context)
        assert "4100000" not in rendered
        assert "4100" not in rendered


def test_every_finding_code_is_stable_and_snake_case() -> None:
    """Clients branch on these, so they are contract, not prose."""
    for code in FindingCode:
        assert code.value.islower()
        assert " " not in code.value


# ---------------------------------------------------------------------------
# The score is reproducible
# ---------------------------------------------------------------------------


def test_the_same_input_always_scores_the_same() -> None:
    """T2.9's requirement, asserted here rather than deferred to the harness.

    This is the reason the score is arithmetic over a fixed table and not a
    second opinion from a model.
    """
    inputs = FinancialInputs(
        monthly_revenue_minor=41_000 * NAIRA, last_12m_revenue_minor=4_100
    )

    scores = {data_integrity_score(check_scale(inputs)) for _ in range(10)}

    assert len(scores) == 1


def test_a_clean_profile_scores_100() -> None:
    assert data_integrity_score([]) == Decimal(100)


def test_a_certain_finding_costs_more_than_a_likely_one() -> None:
    """It cannot be a false positive, so it should weigh more."""
    certain = data_integrity_score(check_team(team_size=2, founder_count=9))
    likely = data_integrity_score(
        check_scale(
            FinancialInputs(
                monthly_revenue_minor=41_000 * NAIRA, last_12m_revenue_minor=4_100
            )
        )
    )

    assert certain < likely


def test_the_score_floors_at_zero() -> None:
    """A profile does not go negative; 0 already means 'rely on none of this'."""
    many = [
        Contradiction(
            summary=f"conflict {n}",
            claim={"source_id": "deck", "quote": "34 customers"},  # type: ignore[arg-type]
            conflicting_claim={"source_id": "xlsx", "quote": "12 customers"},  # type: ignore[arg-type]
        )
        for n in range(20)
    ]

    assert data_integrity_score([], many) == Decimal(0)


@pytest.mark.parametrize("count", [1, 2, 3])
def test_each_contradiction_lowers_the_score(count: int) -> None:
    contradictions = [
        Contradiction(
            summary="conflict",
            claim={"source_id": "deck", "quote": "34"},  # type: ignore[arg-type]
            conflicting_claim={"source_id": "xlsx", "quote": "12"},  # type: ignore[arg-type]
        )
        for _ in range(count)
    ]

    assert data_integrity_score([], contradictions) == Decimal(100) - 20 * count
