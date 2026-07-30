"""Single-use email tokens: verification and password reset.

Only the SHA-256 hash is stored -- the raw value exists once, in the message
that carried it. `purpose` is part of every lookup so a verification token
cannot be presented as a password reset (AUTH.md sections 12, 15).

Rows are consumed by setting `used_at` rather than deleted, so a replay can
be told apart from a token that never existed.

Revision ID: 0004_auth_tokens
Revises: 0003_users
Create Date: 2026-07-29 18:07:43.757617+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0004_auth_tokens'
down_revision: str | None = '0003_users'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('auth_tokens',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('purpose', sa.Enum('email_verification', 'password_reset', name='token_purpose', native_enum=False, length=32), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_auth_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_auth_tokens'))
    )
    op.create_index(op.f('ix_auth_tokens_purpose'), 'auth_tokens', ['purpose'], unique=False)
    op.create_index(op.f('ix_auth_tokens_token_hash'), 'auth_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_auth_tokens_user_id'), 'auth_tokens', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_auth_tokens_user_id'), table_name='auth_tokens')
    op.drop_index(op.f('ix_auth_tokens_token_hash'), table_name='auth_tokens')
    op.drop_index(op.f('ix_auth_tokens_purpose'), table_name='auth_tokens')
    op.drop_table('auth_tokens')
