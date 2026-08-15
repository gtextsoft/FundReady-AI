"""Store Stripe subscription id for monthly founder billing (D24).

Revision ID: 0025_monthly_subscription
Revises: 0024_meeting_proposed
Create Date: 2026-08-15 18:10:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_monthly_subscription"
down_revision: str | None = "0024_meeting_proposed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_users_stripe_subscription_id",
        "users",
        ["stripe_subscription_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_users_stripe_subscription_id", table_name="users")
    op.drop_column("users", "stripe_subscription_id")
