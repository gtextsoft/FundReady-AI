"""Documents.

Metadata only. **The files themselves live in Cloudflare R2** and never in
Postgres (`fundready-prd.md` §7, `DECISIONS.md` D4) -- `storage_key` is the
pointer, and it is server-generated from UUIDs so no client-supplied filename
ever becomes a path.

`owner_id` sits beside `startup_id` rather than being reached through a join,
so `core.ownership.owned_or_404` decides access on this table with the same
call it uses everywhere else (T1.3, `DECISIONS.md` D13). Safe to denormalise:
a document cannot change hands.

`storage_key` is unique -- two rows pointing at one object would mean deleting
a rejected upload silently breaks another document.

Revision ID: 0007_documents
Revises: 0006_startup_profiles
Create Date: 2026-07-30 08:45:10.623309+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0007_documents'
down_revision: str | None = '0006_startup_profiles'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('documents',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('startup_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.Enum('deck', 'financials', 'cap_table', 'other', name='document_kind', native_enum=False, length=16), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('storage_key', sa.String(length=200), nullable=False),
    sa.Column('content_type', sa.String(length=120), nullable=True),
    sa.Column('size_bytes', sa.BigInteger(), nullable=True),
    sa.Column('status', sa.Enum('pending', 'ready', 'rejected', name='document_status', native_enum=False, length=16), nullable=False),
    sa.Column('scan_status', sa.Enum('pending', 'clean', 'infected', 'skipped', name='document_scan_status', native_enum=False, length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_documents_owner_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['startup_id'], ['startup_profiles.id'], name=op.f('fk_documents_startup_id_startup_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_documents')),
    sa.UniqueConstraint('storage_key', name=op.f('uq_documents_storage_key'))
    )
    op.create_index(op.f('ix_documents_kind'), 'documents', ['kind'], unique=False)
    op.create_index(op.f('ix_documents_owner_id'), 'documents', ['owner_id'], unique=False)
    op.create_index(op.f('ix_documents_startup_id'), 'documents', ['startup_id'], unique=False)
    op.create_index(op.f('ix_documents_status'), 'documents', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_documents_status'), table_name='documents')
    op.drop_index(op.f('ix_documents_startup_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_owner_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_kind'), table_name='documents')
    op.drop_table('documents')
