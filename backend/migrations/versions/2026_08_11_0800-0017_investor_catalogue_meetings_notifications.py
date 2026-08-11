"""Investor profile/KYC, catalogue, meetings, notifications, company verify (T3.2–T5.3).

Revision ID: 0017_platform_depth
Revises: 0016_commerce_purchases
Create Date: 2026-08-11 08:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_platform_depth"
down_revision: str | None = "0016_commerce_purchases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("stripe_identity_session_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "startup_profiles",
        sa.Column(
            "company_verification_status",
            sa.String(length=16),
            nullable=False,
            server_default="none",
        ),
    )

    op.create_table(
        "investor_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("firm", sa.String(length=200), nullable=True),
        sa.Column("investor_type", sa.String(length=64), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("linkedin_url", sa.String(length=500), nullable=True),
        sa.Column("thesis_sectors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("thesis_stages", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("thesis_geographies", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ticket_min_minor", sa.BigInteger(), nullable=True),
        sa.Column("ticket_max_minor", sa.BigInteger(), nullable=True),
        sa.Column("ticket_currency", sa.String(length=3), nullable=True),
        sa.Column("risk_notes", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_investor_profiles_user"),
    )
    op.create_index("ix_investor_profiles_user_id", "investor_profiles", ["user_id"])

    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("regions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("gap_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stripe_price_id", sa.String(length=255), nullable=True),
        sa.Column("amount_minor", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("event_starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_location", sa.String(length=300), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_products_slug"),
    )
    op.create_index("ix_products_kind", "products", ["kind"])
    op.create_index("ix_products_active", "products", ["active"])

    op.add_column(
        "readiness_tasks",
        sa.Column("product_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_readiness_tasks_product_id",
        "readiness_tasks",
        "products",
        ["product_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "purchases",
        sa.Column("product_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_purchases_product_id",
        "purchases",
        "products",
        ["product_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "product_enrolments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "product_id", name="uq_product_enrolment"),
    )

    op.create_table(
        "meetings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("interest_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["interest_id"], ["interests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("interest_id", name="uq_meetings_interest"),
    )
    op.create_index("ix_meetings_scheduled_at", "meetings", ["scheduled_at"])

    op.create_table(
        "call_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("interest_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["interest_id"], ["interests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_call_requests_interest_id", "call_requests", ["interest_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.String(length=2000), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])

    op.create_table(
        "watchlist_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investor_id", sa.Uuid(), nullable=False),
        sa.Column("startup_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["investor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["startup_id"], ["startup_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("investor_id", "startup_id", name="uq_watchlist_pair"),
    )


def downgrade() -> None:
    op.drop_table("watchlist_entries")
    op.drop_table("notifications")
    op.drop_table("call_requests")
    op.drop_table("meetings")
    op.drop_table("product_enrolments")
    op.drop_constraint("fk_purchases_product_id", "purchases", type_="foreignkey")
    op.drop_column("purchases", "product_id")
    op.drop_constraint("fk_readiness_tasks_product_id", "readiness_tasks", type_="foreignkey")
    op.drop_column("readiness_tasks", "product_id")
    op.drop_table("products")
    op.drop_table("investor_profiles")
    op.drop_column("startup_profiles", "company_verification_status")
    op.drop_column("users", "stripe_identity_session_id")
