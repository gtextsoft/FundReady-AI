"""Audit runs.

One row per execution of the audit pipeline over one startup profile (T2.8).

`uq_audit_runs_idempotency` is the point of the table, not a detail. D14 says a
repeated run must be safe, and an audit is the most expensive call the platform
makes -- a duplicate is a real charge to a real founder for a verdict they
already have. Keying on **startup + input fingerprint + rubric version** makes a
retry find the existing row. It closes the race an RQ `job_id` cannot: a job id
prevents a duplicate only while the job is in flight and is released the moment
it completes, after which only the database is still saying no.

`rubric_version` is stored rather than derived (D12), so a run stays explainable
once the rubric moves on. It is part of the fingerprint too, so a new rubric
correctly forces a fresh run instead of reusing a verdict formed under different
criteria.

`report` holds the whole synthesised report because a disputed verdict has to be
reconstructable exactly as issued. Tier filtering (CLAUDE.md §4) happens in the
serialiser -- no endpoint returns this column raw.

**No embedding column.** The task lists embeddings, but Anthropic has no
embeddings endpoint and a vector's dimension is provider-specific (1024, 1536,
...), so declaring one here would silently commit to a provider nobody has
chosen. `pgvector` is already a dependency and still unused; adding the column
is one migration once that decision is made.

Revision ID: 0010_audit_runs
Revises: 0009_user_names
Create Date: 2026-08-02 09:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0010_audit_runs'
down_revision: str | None = '0009_user_names'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('audit_runs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('startup_id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Enum('queued', 'running', 'succeeded', 'failed', name='audit_status', native_enum=False, length=16), nullable=False),
    sa.Column('rubric_version', sa.String(length=20), nullable=False),
    sa.Column('input_hash', sa.String(length=64), nullable=False),
    sa.Column('report', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error_code', sa.String(length=60), nullable=True),
    sa.Column('error_message', sa.String(length=500), nullable=True),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_audit_runs_owner_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['startup_id'], ['startup_profiles.id'], name=op.f('fk_audit_runs_startup_id_startup_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_runs')),
    sa.UniqueConstraint('startup_id', 'input_hash', 'rubric_version', name='uq_audit_runs_idempotency')
    )
    op.create_index(op.f('ix_audit_runs_owner_id'), 'audit_runs', ['owner_id'], unique=False)
    op.create_index(op.f('ix_audit_runs_startup_id'), 'audit_runs', ['startup_id'], unique=False)
    op.create_index(op.f('ix_audit_runs_status'), 'audit_runs', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_runs_status'), table_name='audit_runs')
    op.drop_index(op.f('ix_audit_runs_startup_id'), table_name='audit_runs')
    op.drop_index(op.f('ix_audit_runs_owner_id'), table_name='audit_runs')
    op.drop_table('audit_runs')
