"""Transactional email bodies (T1.2a + T5.3).

Security messages (verification, password reset) and product events (audit
ready, task assigned, evidence result, meeting booked, interest update, KYC).

Every message goes out as both HTML and plain text. Plain text is not a
courtesy: some clients render it by preference, and a security email that
arrives as a blank body is a support incident.

**Templates never take the recipient's address or name.** Security templates
render a code and nothing else, so they cannot accidentally place credentials
somewhere they will be logged. Product templates may name event types and
non-secret context (task summary, assessment outcome) but still never receive
the mailbox. The caller supplies the recipient separately.

**Subjects that carry secrets stay free of those secrets.** Product subjects
may name the event type so a lock-screen preview is useful.
"""

from dataclasses import dataclass
from typing import Any

PRODUCT_NAME = "FundReady"


@dataclass(frozen=True, slots=True)
class EmailContent:
    """A rendered message, ready to send."""

    subject: str
    html: str
    text: str


def _wrap(heading: str, body_html: str) -> str:
    """Minimal, inline-styled HTML.

    No external stylesheet or image: mail clients strip the first and block the
    second, and neither is worth the deliverability cost on a security email.
    """
    return (
        '<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;'
        'font-size:15px;line-height:1.5;color:#111">'
        f'<h1 style="font-size:18px;margin:0 0 16px">{heading}</h1>'
        f"{body_html}"
        '<p style="margin-top:24px;font-size:13px;color:#666">'
        f"{PRODUCT_NAME}</p>"
        "</div>"
    )


def verification_email(code: str, ttl_minutes: int) -> EmailContent:
    """Confirm ownership of an email address before any sensitive action.

    A code rather than a link, so the person finishes signing up in the app
    they started in -- and so nothing in this message is clickable, which is
    the shape a phishing email cannot imitate. The digits are spaced out
    visually but sent as one unbroken string, because a client that reflows the
    HTML must not change what gets copied.
    """
    return EmailContent(
        # **The code stays out of the subject**, tempting as the lock-screen
        # preview is. `notifications.service` logs the subject of every message
        # it sends, and a subject also travels through more relay logs than a
        # body -- either would put a live credential somewhere it is kept.
        subject=f"Confirm your {PRODUCT_NAME} email address",
        html=_wrap(
            "Confirm your email address",
            f"<p>Enter this code in the {PRODUCT_NAME} app to finish setting "
            "up your account.</p>"
            '<p style="font-size:32px;font-weight:600;letter-spacing:6px;'
            "margin:24px 0;font-family:ui-monospace,SFMono-Regular,Menlo,"
            f'monospace">{code}</p>'
            f"<p>The code expires in {ttl_minutes} minutes and can be used "
            "once. If you did not create an account, you can ignore this "
            "message -- nobody can use the code without it.</p>",
        ),
        text=(
            f"Enter this code in the {PRODUCT_NAME} app to finish setting up "
            "your account:\n\n"
            f"{code}\n\n"
            f"The code expires in {ttl_minutes} minutes and can be used once. "
            "If you did not create an account, you can ignore this message -- "
            "nobody can use the code without it."
        ),
    )


def password_reset_email(code: str, ttl_minutes: int) -> EmailContent:
    """Reset a forgotten password with a six-digit code.

    A code rather than a link, matching email verification: the person finishes
    in the app they started in, and nothing in this message is clickable. Says
    nothing that would confirm the account exists to someone who merely guessed
    the address -- the message only makes sense to its owner, and the request
    endpoint answers identically either way (AUTH.md section 12).
    """
    return EmailContent(
        # Code stays out of the subject for the same reason as verification:
        # subjects are logged and travel through more relays than the body.
        subject=f"Reset your {PRODUCT_NAME} password",
        html=_wrap(
            "Reset your password",
            f"<p>Enter this code in the {PRODUCT_NAME} app to choose a new "
            "password.</p>"
            '<p style="font-size:32px;font-weight:600;letter-spacing:6px;'
            "margin:24px 0;font-family:ui-monospace,SFMono-Regular,Menlo,"
            f'monospace">{code}</p>'
            f"<p>The code expires in {ttl_minutes} minutes and can be used "
            "once. If you did not ask for this, no action is needed and your "
            "password is unchanged -- nobody can use the code without it.</p>",
        ),
        text=(
            f"Enter this code in the {PRODUCT_NAME} app to choose a new "
            "password:\n\n"
            f"{code}\n\n"
            f"The code expires in {ttl_minutes} minutes and can be used once. "
            "If you did not ask for this, no action is needed and your "
            "password is unchanged -- nobody can use the code without it."
        ),
    )


def welcome_email() -> EmailContent:
    """Sent once, when an address is confirmed and the account goes active.

    Takes no arguments, deliberately. There is nothing worth personalising here,
    and the rule at the top of this module holds: a template that never receives
    personal data cannot leak any.
    """
    return EmailContent(
        subject=f"Welcome to the {PRODUCT_NAME} Community",
        html=_wrap(
            f"Welcome to the {PRODUCT_NAME} Community",
            "<p>Your email address is confirmed and your account is live.</p>"
            "<p>The next step is the assessment. It asks what an investor would "
            "ask -- what the business does, what the numbers say, and what is "
            "holding growth back -- and produces an audited view of how fundable "
            "and how saleable the business is today.</p>"
            "<p>Answer what you know. A half-known profile is the normal case, "
            "and the audit says what it could not see rather than guessing.</p>",
        ),
        text=(
            "Your email address is confirmed and your account is live.\n\n"
            "The next step is the assessment. It asks what an investor would "
            "ask -- what the business does, what the numbers say, and what is "
            "holding growth back -- and produces an audited view of how "
            "fundable and how saleable the business is today.\n\n"
            "Answer what you know. A half-known profile is the normal case, and "
            "the audit says what it could not see rather than guessing."
        ),
    )


def _score_line(score: int | None) -> str:
    """A verdict headline. `None` is not a zero and must never render as one."""
    return f"{score} / 100" if score is not None else "Not enough to tell"


def audit_report_email(report: Any, app_url: str) -> EmailContent:
    """The finished audit, in full, in the message body.

    **This puts a whole report in an inbox, and that is a deliberate product
    decision rather than an oversight.** It is the founder's own report and they
    asked for it there. The cost is real and worth stating in one place: once
    sent, the report persists outside the app, forwards in a tap, and is
    readable by anyone holding the mail provider's API key. Nothing in it is
    investor-tier and nothing describes another company, so the exposure is the
    founder's own material -- but if that trade is revisited, this function is
    the entire surface to change.

    Typed loosely on purpose. `notifications` sits below `audit` in the layer
    order (ARCHITECTURE.md section 3), so importing `FounderReport` here would
    invert it; the caller passes the assembled report and this renders the
    fields it needs.
    """

    def verdict_html(title: str, verdict: Any) -> str:
        thin = ""
        if verdict.unevidenced_dimensions:
            joined = ", ".join(verdict.unevidenced_dimensions)
            thin = (
                '<p style="margin:6px 0 0;font-size:13px;color:#666">'
                f"No evidence for: {joined}.</p>"
            )
        return (
            '<div style="border:1px solid #e5e5e5;border-radius:8px;'
            'padding:14px;margin:0 0 12px">'
            f'<div style="font-size:13px;color:#666">{title}</div>'
            f'<div style="font-size:20px;margin:4px 0 8px">'
            f"{_score_line(verdict.score)}</div>"
            f'<p style="margin:0">{verdict.rationale}</p>'
            f"{thin}</div>"
        )

    def verdict_text(title: str, verdict: Any) -> str:
        lines = [f"{title}: {_score_line(verdict.score)}", verdict.rationale]
        if verdict.unevidenced_dimensions:
            lines.append(
                "No evidence for: " + ", ".join(verdict.unevidenced_dimensions) + "."
            )
        return "\n".join(lines)

    findings_html = "".join(
        f'<li style="margin-bottom:8px"><strong>{f.severity}</strong> &mdash; '
        f"{f.message}</li>"
        for f in report.findings
    )
    actions_html = "".join(
        f'<li style="margin-bottom:8px">{a.action}'
        f'<br><span style="font-size:13px;color:#666">{a.dimension}</span></li>'
        for a in report.action_plan
    )

    sections = [
        "<p>Your assessment is complete. Here it is in full.</p>",
        verdict_html("Fundability", report.fundability),
        verdict_html("Saleability", report.saleability),
    ]
    if findings_html:
        sections.append(
            '<h2 style="font-size:15px;margin:20px 0 8px">What does not add up</h2>'
            f'<ul style="padding-left:18px;margin:0">{findings_html}</ul>'
        )
    if actions_html:
        sections.append(
            '<h2 style="font-size:15px;margin:20px 0 8px">What to do next</h2>'
            f'<ul style="padding-left:18px;margin:0">{actions_html}</ul>'
        )
    sections.append(
        f'<p style="margin-top:20px"><a href="{app_url}">'
        f"Open it in {PRODUCT_NAME}</a></p>"
        '<p style="font-size:13px;color:#666">This report is yours. An investor '
        "only ever sees a summary of it, and only after you and SACI both agree "
        "to an introduction.</p>"
    )

    text_parts = [
        "Your assessment is complete. Here it is in full.",
        verdict_text("Fundability", report.fundability),
        verdict_text("Saleability", report.saleability),
    ]
    if report.findings:
        joined = "\n".join(f"- [{f.severity}] {f.message}" for f in report.findings)
        text_parts.append(f"What does not add up:\n{joined}")
    if report.action_plan:
        joined = "\n".join(f"- {a.action} ({a.dimension})" for a in report.action_plan)
        text_parts.append(f"What to do next:\n{joined}")
    text_parts.append(f"Open it in {PRODUCT_NAME}: {app_url}")
    text_parts.append(
        "This report is yours. An investor only ever sees a summary of it, and "
        "only after you and SACI both agree to an introduction."
    )

    return EmailContent(
        subject=f"Your {PRODUCT_NAME} assessment is ready",
        html=_wrap(f"Your {PRODUCT_NAME} assessment", "".join(sections)),
        text="\n\n".join(text_parts),
    )


def task_assigned_email(task_summary: str, app_url: str) -> EmailContent:
    """A readiness task was raised for the founder."""
    return EmailContent(
        subject=f"New readiness task on {PRODUCT_NAME}",
        html=_wrap(
            "New readiness task",
            f"<p>Your assessment raised something to work on:</p>"
            f'<p style="margin:16px 0"><strong>{task_summary}</strong></p>'
            f'<p><a href="{app_url}">Open it in {PRODUCT_NAME}</a></p>',
        ),
        text=(
            f"Your assessment raised something to work on:\n\n"
            f"{task_summary}\n\n"
            f"Open it in {PRODUCT_NAME}: {app_url}"
        ),
    )


def evidence_result_email(outcome: str, app_url: str) -> EmailContent:
    """Evidence for a readiness task was assessed."""
    return EmailContent(
        subject=f"Evidence assessment result on {PRODUCT_NAME}",
        html=_wrap(
            "Evidence assessment result",
            f"<p>Your uploaded evidence was assessed as "
            f"<strong>{outcome}</strong>.</p>"
            f'<p><a href="{app_url}">Review it in {PRODUCT_NAME}</a></p>',
        ),
        text=(
            f"Your uploaded evidence was assessed as {outcome}.\n\n"
            f"Review it in {PRODUCT_NAME}: {app_url}"
        ),
    )


def meeting_booked_email(when_label: str, app_url: str) -> EmailContent:
    """SACI booked a meeting between founder and investor."""
    return EmailContent(
        subject=f"Meeting booked on {PRODUCT_NAME}",
        html=_wrap(
            "Meeting booked",
            f"<p>A meeting has been scheduled for "
            f"<strong>{when_label}</strong>.</p>"
            f'<p><a href="{app_url}">See details in {PRODUCT_NAME}</a></p>',
        ),
        text=(
            f"A meeting has been scheduled for {when_label}.\n\n"
            f"See details in {PRODUCT_NAME}: {app_url}"
        ),
    )


def interest_update_email(status: str, app_url: str) -> EmailContent:
    """An interest expression changed state (approved, declined, …)."""
    return EmailContent(
        subject=f"Interest update on {PRODUCT_NAME}",
        html=_wrap(
            "Interest update",
            f"<p>An introduction request is now "
            f"<strong>{status}</strong>.</p>"
            f'<p><a href="{app_url}">Open {PRODUCT_NAME}</a></p>',
        ),
        text=(
            f"An introduction request is now {status}.\n\n"
            f"Open {PRODUCT_NAME}: {app_url}"
        ),
    )


def kyc_verified_email(app_url: str) -> EmailContent:
    """Investor identity verification succeeded (Stripe Identity)."""
    return EmailContent(
        subject=f"Identity verified on {PRODUCT_NAME}",
        html=_wrap(
            "Identity verified",
            "<p>Your identity check is complete. You can now browse dealflow "
            "and express interest.</p>"
            f'<p><a href="{app_url}">Open {PRODUCT_NAME}</a></p>',
        ),
        text=(
            "Your identity check is complete. You can now browse dealflow "
            "and express interest.\n\n"
            f"Open {PRODUCT_NAME}: {app_url}"
        ),
    )
