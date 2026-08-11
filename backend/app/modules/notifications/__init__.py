"""Notifications module.

In-app inbox and transactional email for audit, task, evidence, meeting,
interest, and KYC events (T5.3).
"""

from app.modules.notifications.service import create_notification

__all__ = ["create_notification"]
