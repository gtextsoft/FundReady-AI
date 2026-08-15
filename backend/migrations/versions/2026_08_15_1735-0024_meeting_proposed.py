"""Document meeting status `proposed` (VARCHAR, no native enum).

Revision ID: 0024_meeting_proposed
Revises: 0023_rls_backstop
Create Date: 2026-08-15 17:35:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024_meeting_proposed"
down_revision: str | None = "0023_rls_backstop"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        COMMENT ON COLUMN meetings.status IS
        'proposed | scheduled | cancelled'
        """
    )


def downgrade() -> None:
    op.execute("COMMENT ON COLUMN meetings.status IS NULL")
