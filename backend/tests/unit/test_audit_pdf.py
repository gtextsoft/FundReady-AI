"""Founder audit PDF is built from the FounderReport serializer."""

from decimal import Decimal

from app.modules.audit.pdf import render_founder_report_pdf
from app.modules.audit.reports import (
    ActionItemView,
    FinderView,
    FounderReport,
    VerdictDetail,
)


def test_render_founder_report_pdf_is_non_empty_pdf() -> None:
    report = FounderReport(
        rubric_version="v1",
        data_integrity_score=Decimal("85"),
        fundability=VerdictDetail(
            scope="fundability",
            level="provisional",
            score=58,
            sufficiency="provisional",
            rationale="Provisional on thin market evidence.",
            evidenced_dimensions=["financial_health"],
            unevidenced_dimensions=["market_opportunity"],
        ),
        saleability=VerdictDetail(
            scope="saleability",
            level="not_yet",
            score=45,
            sufficiency="sufficient",
            rationale="Saleability not yet ready.",
            evidenced_dimensions=["team"],
            unevidenced_dimensions=[],
        ),
        findings=[
            FinderView(
                code="churn_implausibly_low",
                severity="likely",
                fields=["monthly_churn_percent"],
                message="Churn looks too low for your customer count.",
            )
        ],
        action_plan=[
            ActionItemView(
                dimension="legal_and_ip",
                action="Obtain signed IP assignment.",
                dimension_score=40,
                is_priority=True,
            )
        ],
    )

    pdf = render_founder_report_pdf(
        report, company_name="Kanmi Logistics", run_id="00000000-0000-0000-0000-000000000001"
    )

    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 500
