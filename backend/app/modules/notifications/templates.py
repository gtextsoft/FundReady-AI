"""Transactional email bodies.

Verification and password reset only -- the full templated set (audit ready,
task assigned, evidence result, meeting booked) is T5.3.

Every message goes out as both HTML and plain text. Plain text is not a
courtesy: some clients render it by preference, and a security email that
arrives as a blank body is a support incident.

**Templates never take the recipient's address or name.** They render one
secret -- a verification code or a reset link -- and nothing else, so a
template cannot accidentally place personal data somewhere it will be logged.
The caller supplies the recipient separately.
"""

from dataclasses import dataclass

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


def password_reset_email(reset_url: str) -> EmailContent:
    """Reset a forgotten password.

    Says nothing that would confirm the account exists to someone who merely
    guessed the address -- the message only makes sense to its owner, and the
    request endpoint answers identically either way (AUTH.md section 12).
    """
    return EmailContent(
        subject=f"Reset your {PRODUCT_NAME} password",
        html=_wrap(
            "Reset your password",
            "<p>Use the link below to choose a new password.</p>"
            f'<p><a href="{reset_url}">Reset password</a></p>'
            "<p>The link expires in one hour and can be used once. If you did "
            "not ask for this, no action is needed and your password is "
            "unchanged.</p>",
        ),
        text=(
            "Use the link below to choose a new password:\n\n"
            f"{reset_url}\n\n"
            "The link expires in one hour and can be used once. If you did not "
            "ask for this, no action is needed and your password is unchanged."
        ),
    )
