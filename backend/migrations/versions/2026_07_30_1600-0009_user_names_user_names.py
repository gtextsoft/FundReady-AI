"""User first and last name.

Collected at self-service registration so every founder and investor has one.

**Nullable, deliberately.** Two populations never went through that form:
accounts that existed before this column, and admins, who are provisioned by
another admin (`AUTH.md` §3.2) rather than self-registering. A NOT NULL column
would need a backfill value for both, and a fabricated name is worse than an
absent one -- it reads as data. The API requires both fields on registration,
so "null" means "never asked", not "declined to answer".

**One pair of columns on `users`, not per-role tables.** `users` already holds
founders, investors, and admins distinguished by `role`, so a name is always
attached to a role and the two can never be confused. `startup_profiles.name`
remains the *company* name and is untouched.

Length 100 each: long enough for real names in every script this platform
serves, short enough to bound the row.

**The downgrade discards data.** Dropping these columns deletes every name
collected since the upgrade, and no backup is taken here. It was verified up
and down while the columns were still empty, which proves the SQL is valid --
not that running it later is safe. Export `users.first_name` / `users.last_name`
before downgrading a populated database.

Revision ID: 0009_user_names
Revises: 0008_benchmarks
Create Date: 2026-07-30 16:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0009_user_names'
down_revision: str | None = '0008_benchmarks'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'users', sa.Column('first_name', sa.String(length=100), nullable=True)
    )
    op.add_column(
        'users', sa.Column('last_name', sa.String(length=100), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('users', 'last_name')
    op.drop_column('users', 'first_name')
