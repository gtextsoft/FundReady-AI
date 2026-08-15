"""Bridge revision for databases already stamped `0020_thesis_review`.

Revision ID: 0020_thesis_review
Revises: 0016_commerce_purchases
Create Date: 2026-08-15 02:45:00.000000+00:00

The live Neon branch was stamped past this repo's committed head (0016)
by unmerged work. This revision is a no-op so `alembic upgrade` can
walk from 0016 to the catalogue follow-up without inventing the missing
0017–0019 files. A database that is already at `0020_thesis_review`
skips this file entirely.
"""

from collections.abc import Sequence

revision: str = "0020_thesis_review"
down_revision: str | None = "0016_commerce_purchases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    return


def downgrade() -> None:
    return
