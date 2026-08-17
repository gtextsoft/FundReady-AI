"""Give leftover investor_profiles.id a default.

Revision ID: 0027_investor_profile_id_default
Revises: 0026_investor_review_columns
Create Date: 2026-08-17 12:10:00.000000+00:00

An older `investor_profiles` table used a surrogate `id` primary key.
The ORM treats `user_id` as the PK and does not send `id`, so first-read
`GET /v1/investor/me` failed with a NOT NULL violation. Tables created
from `0022_platform_ops` have no `id` column and are left alone.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0027_investor_profile_id_default"
down_revision: str | None = "0026_investor_review_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'investor_profiles'
              AND column_name = 'id'
          ) THEN
            ALTER TABLE investor_profiles
              ALTER COLUMN id SET DEFAULT gen_random_uuid();
            UPDATE investor_profiles
              SET id = gen_random_uuid()
              WHERE id IS NULL;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'investor_profiles'
              AND column_name = 'id'
          ) THEN
            ALTER TABLE investor_profiles ALTER COLUMN id DROP DEFAULT;
          END IF;
        END $$;
        """
    )
