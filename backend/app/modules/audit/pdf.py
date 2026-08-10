"""Founder-tier audit report PDF (ReportLab).

Pure rendering from a `FounderReport` — the same serializer the JSON endpoint
uses — so the PDF cannot diverge from API tier rules.
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.modules.audit.reports import FounderReport, VerdictDetail


def render_founder_report_pdf(
    report: FounderReport,
    *,
    company_name: str | None,
    run_id: str,
    generated_at: datetime | None = None,
) -> bytes:
    """Build a multi-section PDF for the founder tier."""
    when = generated_at or datetime.now(UTC)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"FundReady audit — {company_name or 'Startup'}",
    )
    styles = _styles()
    story: list = []

    story.append(Paragraph("SACI FundReady", styles["brand"]))
    story.append(Paragraph("Founder audit report", styles["title"]))
    story.append(
        Paragraph(
            f"<b>Company:</b> {_esc(company_name or 'Untitled startup')}<br/>"
            f"<b>Rubric:</b> {_esc(report.rubric_version)}<br/>"
            f"<b>Generated:</b> {_esc(when.strftime('%Y-%m-%d %H:%M UTC'))}<br/>"
            f"<b>Audit run:</b> {_esc(run_id)}",
            styles["body"],
        )
    )
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("1. Data integrity", styles["h1"]))
    story.append(
        Paragraph(
            f"Integrity score: <b>{_esc(str(report.data_integrity_score))}</b> "
            "(how consistent and complete the submitted evidence looked).",
            styles["body"],
        )
    )
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("2. Fundability", styles["h1"]))
    story.extend(_verdict_blocks(report.fundability, styles))

    story.append(Paragraph("3. Saleability", styles["h1"]))
    story.extend(_verdict_blocks(report.saleability, styles))

    story.append(Paragraph("4. Findings", styles["h1"]))
    if not report.findings:
        story.append(Paragraph("No findings were raised.", styles["body"]))
    else:
        by_sev: dict[str, list] = {}
        for finding in report.findings:
            by_sev.setdefault(finding.severity, []).append(finding)
        for severity in ("certain", "likely", "possible", "info"):
            group = by_sev.get(severity) or []
            if not group:
                continue
            story.append(Paragraph(severity.replace("_", " ").title(), styles["h2"]))
            for finding in group:
                fields = ", ".join(finding.fields) if finding.fields else "—"
                story.append(
                    Paragraph(
                        f"<b>{_esc(finding.code)}</b> — {_esc(finding.message)} "
                        f"<i>(fields: {_esc(fields)})</i>",
                        styles["body"],
                    )
                )
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("5. Action plan", styles["h1"]))
    priorities = [a for a in report.action_plan if a.is_priority]
    rest = [a for a in report.action_plan if not a.is_priority]
    if priorities:
        story.append(Paragraph("Priorities", styles["h2"]))
        story.extend(_action_rows(priorities))
    if rest:
        story.append(Paragraph("Full plan", styles["h2"]))
        story.extend(_action_rows(rest))
    if not report.action_plan:
        story.append(Paragraph("No action items in this report.", styles["body"]))

    story.append(Spacer(1, 8 * mm))
    story.append(
        Paragraph(
            "Disclaimer: This report is an automated readiness assessment for the "
            "founder. It is not investment advice, a credit decision, or a "
            "guarantee of funding or acquisition outcomes. Scores marked "
            "<b>insufficient_data</b> mean the company was not assessed on that "
            "axis — not that it failed.",
            styles["disclaimer"],
        )
    )

    doc.build(story)
    return buffer.getvalue()


def _verdict_blocks(verdict: VerdictDetail, styles: dict) -> list:
    blocks: list = []
    score_text = (
        "insufficient evidence"
        if verdict.level == "insufficient_data" or verdict.score is None
        else str(verdict.score)
    )
    blocks.append(
        Paragraph(
            f"Level: <b>{_esc(verdict.level)}</b> · Score: <b>{_esc(score_text)}</b> · "
            f"Sufficiency: {_esc(verdict.sufficiency)}",
            styles["body"],
        )
    )
    blocks.append(Paragraph(_esc(verdict.rationale), styles["body"]))
    if verdict.evidenced_dimensions:
        blocks.append(
            Paragraph(
                "<b>Evidenced:</b> "
                + _esc(", ".join(verdict.evidenced_dimensions)),
                styles["body"],
            )
        )
    if verdict.unevidenced_dimensions:
        blocks.append(
            Paragraph(
                "<b>Unevidenced (fill these next):</b> "
                + _esc(", ".join(verdict.unevidenced_dimensions)),
                styles["body"],
            )
        )
    blocks.append(Spacer(1, 4 * mm))
    return blocks


def _action_rows(items: list) -> list:
    data = [["Dimension", "Score", "Action"]]
    for item in items:
        score = "—" if item.dimension_score is None else str(item.dimension_score)
        data.append([item.dimension, score, item.action])
    table = Table(data, colWidths=[40 * mm, 18 * mm, 112 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a2332")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return [table, Spacer(1, 3 * mm)]


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "brand",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=colors.HexColor("#0b6e4f"),
            alignment=TA_LEFT,
            spaceAfter=2,
        ),
        "title": ParagraphStyle(
            "title",
            parent=base["Heading1"],
            fontSize=16,
            spaceAfter=8,
            textColor=colors.HexColor("#1a2332"),
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading2"],
            fontSize=12,
            spaceBefore=6,
            spaceAfter=4,
            textColor=colors.HexColor("#1a2332"),
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading3"],
            fontSize=10,
            spaceBefore=4,
            spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            spaceAfter=3,
        ),
        "disclaimer": ParagraphStyle(
            "disclaimer",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#555555"),
            alignment=TA_CENTER,
        ),
    }


def _esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
