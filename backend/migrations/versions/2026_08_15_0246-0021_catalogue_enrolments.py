"""Catalogue tables for T3.2. Idempotent: the live DB already has `products`.

Revision ID: 0021_catalogue_enrolments
Revises: 0020_thesis_review
Create Date: 2026-08-15 02:46:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021_catalogue_enrolments"
down_revision: str | None = "0020_thesis_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id UUID NOT NULL,
            kind VARCHAR(32) NOT NULL,
            slug VARCHAR(80) NOT NULL,
            title VARCHAR(200) NOT NULL,
            description TEXT NOT NULL,
            regions JSONB NOT NULL DEFAULT '[]'::jsonb,
            gap_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            amount_minor INTEGER,
            currency VARCHAR(3),
            stripe_price_id VARCHAR(255),
            event_starts_at TIMESTAMPTZ,
            event_location VARCHAR(200),
            active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            UNIQUE (slug)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_products_kind ON products (kind)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS enrolments (
            id UUID NOT NULL,
            user_id UUID NOT NULL,
            product_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT uq_enrolments_user_product UNIQUE (user_id, product_id),
            CONSTRAINT fk_enrolments_user_id
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            CONSTRAINT fk_enrolments_product_id
                FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_enrolments_user_id ON enrolments (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_enrolments_product_id ON enrolments (product_id)"
    )

    op.execute(
        "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS product_id UUID"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_purchases_product_id ON purchases (product_id)"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_purchases_product_id'
            ) THEN
                ALTER TABLE purchases
                    ADD CONSTRAINT fk_purchases_product_id
                    FOREIGN KEY (product_id) REFERENCES products (id)
                    ON DELETE SET NULL;
            END IF;
        END $$
        """
    )

    op.execute(
        "ALTER TABLE readiness_tasks ADD COLUMN IF NOT EXISTS product_id UUID"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_readiness_tasks_product_id "
        "ON readiness_tasks (product_id)"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_readiness_tasks_product_id'
            ) THEN
                ALTER TABLE readiness_tasks
                    ADD CONSTRAINT fk_readiness_tasks_product_id
                    FOREIGN KEY (product_id) REFERENCES products (id)
                    ON DELETE SET NULL;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE readiness_tasks DROP CONSTRAINT IF EXISTS "
        "fk_readiness_tasks_product_id"
    )
    op.drop_index("ix_readiness_tasks_product_id", table_name="readiness_tasks")
    op.drop_column("readiness_tasks", "product_id")

    op.execute("ALTER TABLE purchases DROP CONSTRAINT IF EXISTS fk_purchases_product_id")
    op.drop_index("ix_purchases_product_id", table_name="purchases")
    op.drop_column("purchases", "product_id")

    op.drop_index("ix_enrolments_product_id", table_name="enrolments")
    op.drop_index("ix_enrolments_user_id", table_name="enrolments")
    op.drop_table("enrolments")

    op.drop_index("ix_products_kind", table_name="products")
    op.drop_table("products")
