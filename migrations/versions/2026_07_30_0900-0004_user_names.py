"""Personal names on the user record.

Collected at registration so the app can address someone by name instead of
guessing one from their email local-part.

Not in `AUTH.md` section 15 -- this is an additive product change, requested
after that spec was written. Additive is the operative word: both columns carry
an empty-string default, so rows created before this migration remain valid and
no code has to branch on NULL.

These are PII. They are readable by their owner and by an admin, never by
another tenant, and never written to a log (CLAUDE.md section 4).

Revision ID: 0004_user_names
Revises: 0003_users
Create Date: 2026-07-30 09:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_user_names"
down_revision: str | None = "0003_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("first_name", sa.String(length=80), nullable=False, server_default=""),
    )
    op.add_column(
        "users",
        sa.Column("last_name", sa.String(length=80), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
