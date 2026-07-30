"""Benchmarks.

The knowledge base every financial figure is compared against (T2.3), keyed by
**sector x stage x metric x region** as the PRD specifies.

`sector` and `region` accept the wildcard `*`, which is what lets the lookup
fall back from "Nigerian last-mile delivery" to "any sector, Nigeria" to "any
sector, globally". Sector is free text because D11 requires accepting sectors
that do not exist yet, so exact matches often miss and the fallback is the
normal path rather than an edge case.

Quartiles rather than a single median: a rubric asking "is this good" needs a
band, and adding p25/p75 later would be a migration on a table already holding
hand-curated rows.

`source` and `as_of_date` are NOT NULL on purpose. `CLAUDE.md` §5 forbids a
verdict without citable evidence, and benchmarks go stale -- a date is what
makes that visible instead of silent.

The unique key stops two rows serving one cell, which would let query order
decide a verdict.

Revision ID: 0008_benchmarks
Revises: 0007_documents
Create Date: 2026-07-30 11:05:40.693404+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0008_benchmarks'
down_revision: str | None = '0007_documents'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('benchmarks',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('sector', sa.String(length=120), nullable=False),
    sa.Column('stage', sa.Enum('idea', 'pre_seed', 'seed', 'series_a', 'series_b_plus', 'growth', name='startup_stage', native_enum=False, length=16), nullable=False),
    sa.Column('metric', sa.Enum('gross_margin_percent', 'runway_months', 'ltv_cac_ratio', 'cac_payback_months', 'run_rate_vs_trailing_percent', name='benchmark_metric', native_enum=False, length=40), nullable=False),
    sa.Column('region', sa.String(length=2), nullable=False),
    sa.Column('p25', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('p50', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('p75', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('sample_size', sa.Integer(), nullable=True),
    sa.Column('source', sa.String(length=300), nullable=False),
    sa.Column('as_of_date', sa.Date(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_benchmarks')),
    sa.UniqueConstraint('sector', 'stage', 'metric', 'region', name='uq_benchmarks_key')
    )
    op.create_index(op.f('ix_benchmarks_is_active'), 'benchmarks', ['is_active'], unique=False)
    op.create_index(op.f('ix_benchmarks_metric'), 'benchmarks', ['metric'], unique=False)
    op.create_index(op.f('ix_benchmarks_region'), 'benchmarks', ['region'], unique=False)
    op.create_index(op.f('ix_benchmarks_sector'), 'benchmarks', ['sector'], unique=False)
    op.create_index(op.f('ix_benchmarks_stage'), 'benchmarks', ['stage'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_benchmarks_stage'), table_name='benchmarks')
    op.drop_index(op.f('ix_benchmarks_sector'), table_name='benchmarks')
    op.drop_index(op.f('ix_benchmarks_region'), table_name='benchmarks')
    op.drop_index(op.f('ix_benchmarks_metric'), table_name='benchmarks')
    op.drop_index(op.f('ix_benchmarks_is_active'), table_name='benchmarks')
    op.drop_table('benchmarks')
