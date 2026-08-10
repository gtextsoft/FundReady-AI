"""The welcome message and the finished-audit report, as rendered.

These two are unlike the verification and reset messages: they carry no secret,
so the risk they pose is not disclosure of a credential but disclosure of the
founder's own report to whatever holds the mailbox. The report body is a
deliberate product decision (see `audit_report_email`), and what these tests
protect is that it says what it means -- above all that a verdict the audit
declined to score never renders as a zero.
"""

from dataclasses import dataclass

from app.modules.notifications.templates import (
    PRODUCT_NAME,
    audit_report_email,
    welcome_email,
)

APP_URL = "https://app.fundready.test"


@dataclass(frozen=True)
class FakeVerdict:
    score: int | None
    rationale: str
    unevidenced_dimensions: list[str]


@dataclass(frozen=True)
class FakeFinding:
    severity: str
    message: str
    fields: list[str]


@dataclass(frozen=True)
class FakeAction:
    dimension: str
    action: str
    dimension_score: int | None = None
    is_priority: bool = False


@dataclass(frozen=True)
class FakeReport:
    fundability: FakeVerdict
    saleability: FakeVerdict
    findings: list[FakeFinding]
    action_plan: list[FakeAction]


def scored_report() -> FakeReport:
    return FakeReport(
        fundability=FakeVerdict(58, "Provisional on the evidence available.", []),
        saleability=FakeVerdict(
            41, "Owner dependency is high.", ["market_opportunity"]
        ),
        findings=[
            FakeFinding(
                "likely", "Your monthly churn is under 0.1%.", ["monthly_churn_percent"]
            )
        ],
        action_plan=[
            FakeAction(
                "financial_health", "Publish a 12-month cash forecast.", 40, True
            )
        ],
    )


class TestWelcome:
    def test_subject_is_the_one_asked_for(self) -> None:
        assert welcome_email().subject == f"Welcome to the {PRODUCT_NAME} Community"

    def test_carries_no_personal_data(self) -> None:
        # The template takes no arguments at all, which is what makes this
        # true by construction rather than by inspection.
        content = welcome_email()
        for body in (content.html, content.text):
            assert "@" not in body

    def test_has_both_bodies(self) -> None:
        content = welcome_email()
        assert content.html.strip()
        assert content.text.strip()
        # A client that prefers plain text must not get an empty message.
        assert "assessment" in content.text.lower()


class TestAuditReport:
    def test_renders_both_verdicts_and_the_plan(self) -> None:
        content = audit_report_email(scored_report(), APP_URL)

        assert content.subject == f"Your {PRODUCT_NAME} assessment is ready"
        for body in (content.html, content.text):
            assert "58" in body
            assert "41" in body
            assert "Owner dependency is high." in body
            assert "Publish a 12-month cash forecast." in body
            assert "churn" in body.lower()

    def test_a_verdict_with_no_score_is_never_a_zero(self) -> None:
        # The audit returning `None` means it declined to reach a number.
        # Printing "0 / 100" would state a conclusion it refused to draw, and
        # it is the single most damaging thing this template could get wrong.
        report = FakeReport(
            fundability=FakeVerdict(
                None, "Not enough evidence to reach a verdict.", ["traction"]
            ),
            saleability=FakeVerdict(
                None, "Not enough evidence to reach a verdict.", []
            ),
            findings=[],
            action_plan=[],
        )
        content = audit_report_email(report, APP_URL)

        for body in (content.html, content.text):
            assert "Not enough to tell" in body
            assert "0 / 100" not in body
            assert "0/100" not in body

    def test_says_what_the_audit_could_not_see(self) -> None:
        content = audit_report_email(scored_report(), APP_URL)
        for body in (content.html, content.text):
            assert "market_opportunity" in body

    def test_survives_a_report_with_no_findings_or_actions(self) -> None:
        report = FakeReport(
            fundability=FakeVerdict(70, "Clear.", []),
            saleability=FakeVerdict(70, "Clear.", []),
            findings=[],
            action_plan=[],
        )
        content = audit_report_email(report, APP_URL)
        # No empty section headings left behind.
        assert "What does not add up" not in content.html
        assert "What to do next" not in content.html
        assert "70" in content.text

    def test_links_back_into_the_app(self) -> None:
        content = audit_report_email(scored_report(), APP_URL)
        assert APP_URL in content.html
        assert APP_URL in content.text

    def test_states_that_no_investor_sees_this(self) -> None:
        # The report is in an inbox now. Saying plainly that it is not shared
        # is the least this message owes the founder.
        content = audit_report_email(scored_report(), APP_URL)
        for body in (content.html, content.text):
            assert "investor" in body.lower()
