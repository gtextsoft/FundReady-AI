"""Enable RLS policies as a backstop. Table owner still bypasses (D19).

Revision ID: 0023_rls_backstop
Revises: 0022_platform_ops
Create Date: 2026-08-15 16:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023_rls_backstop"
down_revision: str | None = "0022_platform_ops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ENABLE without FORCE: the migration/table owner still bypasses, so local
# tests and the current Neon role are unchanged. A least-privilege
# `fundready_app` role with NOBYPASSRLS is an ops step — see docs/DEPLOY.md.


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE startup_profiles ENABLE ROW LEVEL SECURITY;
        ALTER TABLE investor_profiles ENABLE ROW LEVEL SECURITY;
        ALTER TABLE watchlist_items ENABLE ROW LEVEL SECURITY;
        ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
        ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE tablename = 'startup_profiles' AND policyname = 'startup_profiles_owner'
          ) THEN
            CREATE POLICY startup_profiles_owner ON startup_profiles
              USING (owner_id::text = current_setting('app.current_user_id', true));
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE tablename = 'investor_profiles' AND policyname = 'investor_profiles_self'
          ) THEN
            CREATE POLICY investor_profiles_self ON investor_profiles
              USING (user_id::text = current_setting('app.current_user_id', true));
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE tablename = 'watchlist_items' AND policyname = 'watchlist_items_self'
          ) THEN
            CREATE POLICY watchlist_items_self ON watchlist_items
              USING (investor_id::text = current_setting('app.current_user_id', true));
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE tablename = 'notifications' AND policyname = 'notifications_self'
          ) THEN
            CREATE POLICY notifications_self ON notifications
              USING (user_id::text = current_setting('app.current_user_id', true));
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE tablename = 'meetings' AND policyname = 'meetings_visible'
          ) THEN
            CREATE POLICY meetings_visible ON meetings
              USING (
                EXISTS (
                  SELECT 1 FROM interests
                  WHERE interests.id = meetings.interest_id
                    AND interests.investor_id::text
                      = current_setting('app.current_user_id', true)
                )
              );
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP POLICY IF EXISTS meetings_visible ON meetings;
        DROP POLICY IF EXISTS notifications_self ON notifications;
        DROP POLICY IF EXISTS watchlist_items_self ON watchlist_items;
        DROP POLICY IF EXISTS investor_profiles_self ON investor_profiles;
        DROP POLICY IF EXISTS startup_profiles_owner ON startup_profiles;
        ALTER TABLE meetings DISABLE ROW LEVEL SECURITY;
        ALTER TABLE notifications DISABLE ROW LEVEL SECURITY;
        ALTER TABLE watchlist_items DISABLE ROW LEVEL SECURITY;
        ALTER TABLE investor_profiles DISABLE ROW LEVEL SECURITY;
        ALTER TABLE startup_profiles DISABLE ROW LEVEL SECURITY;
        """
    )
