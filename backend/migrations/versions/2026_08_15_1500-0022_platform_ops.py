"""Investor profiles, watchlist, meetings, notifications, company verification.

Revision ID: 0022_platform_ops
Revises: 0021_catalogue_enrolments
Create Date: 2026-08-15 15:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022_platform_ops"
down_revision: str | None = "0021_catalogue_enrolments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE startup_profiles
        ADD COLUMN IF NOT EXISTS company_verification_status VARCHAR(16)
        NOT NULL DEFAULT 'none'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_startup_profiles_company_verification
        ON startup_profiles (company_verification_status)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS investor_profiles (
            user_id UUID NOT NULL,
            firm VARCHAR(200),
            investor_type VARCHAR(80),
            country VARCHAR(2),
            linkedin_url VARCHAR(400),
            thesis_sectors JSONB NOT NULL DEFAULT '[]'::jsonb,
            thesis_stages JSONB NOT NULL DEFAULT '[]'::jsonb,
            thesis_geographies JSONB NOT NULL DEFAULT '[]'::jsonb,
            ticket_min_minor INTEGER,
            ticket_max_minor INTEGER,
            ticket_currency VARCHAR(3),
            risk_notes VARCHAR(2000),
            review_status VARCHAR(16) NOT NULL DEFAULT 'none',
            reviewed_at TIMESTAMPTZ,
            reviewed_by_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id),
            CONSTRAINT fk_investor_profiles_user_id
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_investor_profiles_review_status
        ON investor_profiles (review_status)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist_items (
            id UUID NOT NULL,
            investor_id UUID NOT NULL,
            startup_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT fk_watchlist_investor_id
                FOREIGN KEY (investor_id) REFERENCES users (id) ON DELETE CASCADE,
            CONSTRAINT fk_watchlist_startup_id
                FOREIGN KEY (startup_id) REFERENCES startup_profiles (id)
                ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_watchlist_pair
        ON watchlist_items (investor_id, startup_id)
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_watchlist_investor_id ON watchlist_items (investor_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS meetings (
            id UUID NOT NULL,
            interest_id UUID NOT NULL,
            scheduled_at TIMESTAMPTZ NOT NULL,
            duration_minutes INTEGER NOT NULL,
            location VARCHAR(400),
            notes VARCHAR(2000),
            status VARCHAR(16) NOT NULL DEFAULT 'scheduled',
            created_by_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT fk_meetings_interest_id
                FOREIGN KEY (interest_id) REFERENCES interests (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_meetings_interest_id ON meetings (interest_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id UUID NOT NULL,
            user_id UUID NOT NULL,
            kind VARCHAR(40) NOT NULL,
            title VARCHAR(200) NOT NULL,
            body VARCHAR(2000) NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            read_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT fk_notifications_user_id
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notifications_created_at ON notifications (created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notifications")
    op.execute("DROP TABLE IF EXISTS meetings")
    op.execute("DROP TABLE IF EXISTS watchlist_items")
    op.execute("DROP TABLE IF EXISTS investor_profiles")
    op.execute(
        "ALTER TABLE startup_profiles DROP COLUMN IF EXISTS company_verification_status"
    )
