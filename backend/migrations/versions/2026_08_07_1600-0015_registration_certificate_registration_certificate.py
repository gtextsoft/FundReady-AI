"""Widen documents.kind for registration_certificate (T1.6).

`registration_certificate` is 24 characters and the column was VARCHAR(16),
so it could not store the value even though the Python enum accepts it.
Bumped to 32 rather than 24 so the next kind added needs no second widening.

There is no check constraint to rewrite: migration 0007 created the column
as `sa.Enum(..., native_enum=False)` with SQLAlchemy's default
`create_constraint=False`, so validation is application-side only.

Revision ID: 0015_registration_certificate
Revises: 0014_verification_codes
Create Date: 2026-08-07 16:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_registration_certificate"
down_revision: str | None = "0014_verification_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "documents",
        "kind",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Remap first: a 24-character value will not fit back into VARCHAR(16).
    op.execute(
        "UPDATE documents SET kind = 'other' "
        "WHERE kind = 'registration_certificate'"
    )
    op.alter_column(
        "documents",
        "kind",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
