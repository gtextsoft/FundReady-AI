"""Immutable audit log.

Creates `audit_log` and makes it append-only **in the database**, not by
convention. Required by the PRD (section 5), `CLAUDE.md` section 4, and
`AUTH.md` sections 9/13/15.

Three separate guards, because each one alone has a hole:

1. A row-level trigger rejecting UPDATE and DELETE. This is the one that
   matters -- unlike a REVOKE, it also stops the table owner, and every
   connection in this deployment is currently the owner.
2. A statement-level trigger rejecting TRUNCATE, which row-level triggers do
   not see. Without it, the whole log can be erased in one statement.
3. REVOKE from PUBLIC, which takes effect once a least-privilege application
   role exists (T5.7).

Residual hole, stated plainly: a superuser or the table owner can
`ALTER TABLE audit_log DISABLE TRIGGER ALL`. Closing that needs role
separation, which belongs with deployment rather than here. What these guards
do buy is that no ordinary application bug, migration, or careless query can
rewrite history.

Revision ID: 0002_audit_log
Revises: 0001_baseline
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_audit_log"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


IMMUTABILITY_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_log_reject_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'audit_log is append-only; % is not permitted', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        # No foreign key on purpose: the log must outlive the user it refers
        # to. An FK would either block that deletion or cascade the evidence
        # away with them.
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_actor_id"), "audit_log", ["actor_id"])
    op.create_index(op.f("ix_audit_log_action"), "audit_log", ["action"])
    op.create_index(op.f("ix_audit_log_target_id"), "audit_log", ["target_id"])
    op.create_index(op.f("ix_audit_log_created_at"), "audit_log", ["created_at"])

    op.execute(IMMUTABILITY_FUNCTION)
    op.execute(
        """
        CREATE TRIGGER audit_log_no_update_or_delete
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_reject_mutation();
        """
    )
    # TRUNCATE does not fire row-level triggers, so it needs its own.
    op.execute(
        """
        CREATE TRIGGER audit_log_no_truncate
        BEFORE TRUNCATE ON audit_log
        FOR EACH STATEMENT EXECUTE FUNCTION audit_log_reject_mutation();
        """
    )
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update_or_delete ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_reject_mutation()")
    op.drop_index(op.f("ix_audit_log_created_at"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_target_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_action"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_actor_id"), table_name="audit_log")
    op.drop_table("audit_log")
