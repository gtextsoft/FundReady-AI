"""MFA recovery codes, and TOTP replay protection.

`mfa_recovery_codes` holds ten single-use codes per user, Argon2id-hashed
exactly like passwords -- they are credentials, and a leaked set is a
standing bypass of the second factor.

`users.mfa_last_used_step` records the last TOTP step consumed. Refusing a
code from that step or earlier is what stops an intercepted code being
replayed inside its own 30-second window (AUTH.md section 9.1).

Revision ID: 0005_mfa
Revises: 0004_auth_tokens
Create Date: 2026-07-29 21:28:39.663532+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0005_mfa'
down_revision: str | None = '0004_auth_tokens'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('mfa_recovery_codes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('code_hash', sa.String(length=255), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_mfa_recovery_codes_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_mfa_recovery_codes'))
    )
    op.create_index(op.f('ix_mfa_recovery_codes_user_id'), 'mfa_recovery_codes', ['user_id'], unique=False)
    op.add_column('users', sa.Column('mfa_last_used_step', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'mfa_last_used_step')
    op.drop_index(op.f('ix_mfa_recovery_codes_user_id'), table_name='mfa_recovery_codes')
    op.drop_table('mfa_recovery_codes')
