"""Email verification moves from a link to a six-digit code.

Adds `auth_tokens.attempt_count`, which is what makes a six-digit secret safe
to accept: the code is burned after a handful of wrong guesses, so the million
combinations cannot be walked (AUTH.md section 3.2).

**Outstanding verification links are burned on upgrade.** Their rows hold a
bare SHA-256 of a random token, while a code is stored as a keyed HMAC, so an
old link could never match the new lookup anyway -- consuming the rows makes
that explicit rather than leaving them to expire looking live. Password reset
is untouched and still uses links.

Revision ID: 0014_verification_codes
Revises: 0013_evidence
Create Date: 2026-08-07 14:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0014_verification_codes'
down_revision: str | None = '0013_evidence'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'auth_tokens',
        sa.Column(
            'attempt_count', sa.Integer(), server_default='0', nullable=False
        ),
    )
    op.execute(
        "update auth_tokens set used_at = now() "
        "where purpose = 'email_verification' and used_at is null"
    )


def downgrade() -> None:
    # The burned links are not restored: they were single-use secrets, and
    # reviving one would be reviving a credential.
    op.drop_column('auth_tokens', 'attempt_count')
