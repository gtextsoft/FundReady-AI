"""Startup profiles.

The first founder-owned table, and therefore the first thing tenant
isolation has to protect (T1.3, DECISIONS.md D13).

Indexed columns only for what other subsystems filter on -- benchmarks are
keyed by sector x stage x region (T2.3) and discovery filters on the same
(T4.3). Everything else lives in a JSONB document where each field carries
its own source and confidence, because extraction (T2.4) fills them in with
varying certainty and the canonical field list is still provisional.

`owner_id` is unique: one profile per founder in v1.

Revision ID: 0006_startup_profiles
Revises: 0005_mfa
Create Date: 2026-07-30 00:02:43.050153+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
revision: str = '0006_startup_profiles'
down_revision: str | None = '0005_mfa'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('startup_profiles',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=True),
    sa.Column('sector', sa.String(length=120), nullable=True),
    sa.Column('stage', sa.Enum('idea', 'pre_seed', 'seed', 'series_a', 'series_b_plus', 'growth', name='startup_stage', native_enum=False, length=16), nullable=True),
    sa.Column('country', sa.String(length=2), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('fields', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_startup_profiles_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_startup_profiles'))
    )
    op.create_index(op.f('ix_startup_profiles_country'), 'startup_profiles', ['country'], unique=False)
    op.create_index(op.f('ix_startup_profiles_owner_id'), 'startup_profiles', ['owner_id'], unique=True)
    op.create_index(op.f('ix_startup_profiles_sector'), 'startup_profiles', ['sector'], unique=False)
    op.create_index(op.f('ix_startup_profiles_stage'), 'startup_profiles', ['stage'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_startup_profiles_stage'), table_name='startup_profiles')
    op.drop_index(op.f('ix_startup_profiles_sector'), table_name='startup_profiles')
    op.drop_index(op.f('ix_startup_profiles_owner_id'), table_name='startup_profiles')
    op.drop_index(op.f('ix_startup_profiles_country'), table_name='startup_profiles')
    op.drop_table('startup_profiles')
