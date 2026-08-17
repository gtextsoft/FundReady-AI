"""Add missing investor thesis review columns.

Revision ID: 0026_investor_review_columns
Revises: 0025_monthly_subscription
Create Date: 2026-08-17 12:00:00.000000+00:00

`0022_platform_ops` created `investor_profiles` with `CREATE TABLE IF NOT
EXISTS`. Databases that already had an older copy of the table kept that
shape, so `reviewed_at` / `reviewed_by_id` were never added. Loading a
thesis then 500s the whole investor desk.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026_investor_review_columns"
down_revision: str | None = "0025_monthly_subscription"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE investor_profiles
        ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        ALTER TABLE investor_profiles
        ADD COLUMN IF NOT EXISTS reviewed_by_id UUID
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE investor_profiles DROP COLUMN IF EXISTS reviewed_by_id"
    )
    op.execute(
        "ALTER TABLE investor_profiles DROP COLUMN IF EXISTS reviewed_at"
    )
