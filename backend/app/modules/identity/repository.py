"""Identity data access.

Layer: **repository** (ARCHITECTURE.md section 3) -- database access only.
Queries in, models/data out. No business rules, no authorization decisions.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, CursorResult, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AccountStatus, Role
from app.modules.identity.models import (
    AuditLog,
    AuthToken,
    MfaRecoveryCode,
    RefreshToken,
    TokenPurpose,
    User,
)


class AuditLogRepository:
    """Append and read the audit log.

    **There is deliberately no update or delete method.** The database rejects
    both, but the absence of a callable is the first line of defence: code that
    cannot be written cannot be reviewed carelessly and merged.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        action: str,
        actor_id: uuid.UUID | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details or {},
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list_for_target(
        self, *, target_type: str, target_id: str, limit: int = 100
    ) -> Sequence[AuditLog]:
        statement = (
            select(AuditLog)
            .where(AuditLog.target_type == target_type, AuditLog.target_id == target_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return (await self._session.scalars(statement)).all()

    async def list_for_actor(
        self, *, actor_id: uuid.UUID, limit: int = 100
    ) -> Sequence[AuditLog]:
        statement = (
            select(AuditLog)
            .where(AuditLog.actor_id == actor_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return (await self._session.scalars(statement)).all()


class UserRepository:
    """Read and write user records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        """Look up by an already-normalised email (the service normalises)."""
        result: User | None = await self._session.scalar(
            select(User).where(User.email == email)
        )
        return result

    async def count_admins(self, *, active_only: bool = True) -> int:
        """How many admin accounts exist.

        `active_only` (the default) answers "how many can act right now", which
        is what the never-zero-admins guard needs. The bootstrap script asks
        with `active_only=False`: a just-created admin is still
        `pending_verification`, and counting only active ones would let it
        create a second first-admin.
        """
        conditions = [User.role == Role.ADMIN]
        if active_only:
            conditions.append(User.status == AccountStatus.ACTIVE)
        result = await self._session.scalar(
            select(func.count()).select_from(User).where(*conditions)
        )
        return int(result or 0)

    async def count_active_admins(self) -> int:
        """How many admins can currently act.

        Used to refuse an action that would leave the platform with none, whose
        only remedy is database credentials and a script.
        """
        result = await self._session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == Role.ADMIN, User.status == AccountStatus.ACTIVE)
        )
        return int(result or 0)

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        role: Role,
        status: AccountStatus,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            role=role,
            status=status,
            first_name=first_name,
            last_name=last_name,
        )
        self._session.add(user)
        await self._session.flush()
        return user


class RefreshTokenRepository:
    """Store and revoke refresh tokens.

    Tokens are looked up by hash -- the raw value is never stored, so it is
    never available to be leaked from here.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        family_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result: RefreshToken | None = await self._session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result

    async def mark_used(
        self, token: RefreshToken, *, replaced_by_id: uuid.UUID, at: datetime
    ) -> None:
        token.used_at = at
        token.replaced_by_id = replaced_by_id
        await self._session.flush()

    async def revoke_family(self, family_id: uuid.UUID, *, at: datetime) -> int:
        """Revoke every token descended from one login. Returns the count."""
        return await self._revoke(RefreshToken.family_id == family_id, at=at)

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, at: datetime) -> int:
        """Revoke every session a user has. Returns the count."""
        return await self._revoke(RefreshToken.user_id == user_id, at=at)

    async def _revoke(self, condition: ColumnElement[bool], *, at: datetime) -> int:
        """Revoke every still-live token matching `condition`."""
        result = await self._session.execute(
            update(RefreshToken)
            .where(condition, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=at)
        )
        await self._session.flush()
        # `execute` is typed as returning Result, but an UPDATE always yields a
        # CursorResult, which is what carries rowcount.
        return cast("CursorResult[Any]", result).rowcount


class AuthTokenRepository:
    """Single-use email tokens: verification and password reset."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        purpose: TokenPurpose,
        token_hash: str,
        expires_at: datetime,
    ) -> AuthToken:
        token = AuthToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def get(self, *, token_hash: str, purpose: TokenPurpose) -> AuthToken | None:
        """Look up by hash **and** purpose.

        Both, always: a verification token must not be usable as a password
        reset just because the hash matches.
        """
        result: AuthToken | None = await self._session.scalar(
            select(AuthToken).where(
                AuthToken.token_hash == token_hash, AuthToken.purpose == purpose
            )
        )
        return result

    async def mark_used(self, token: AuthToken, *, at: datetime) -> None:
        token.used_at = at
        await self._session.flush()

    async def consume_outstanding(
        self, *, user_id: uuid.UUID, purpose: TokenPurpose, at: datetime
    ) -> int:
        """Burn every unused token of this purpose for this user.

        A completed reset must invalidate any other reset links already sent --
        otherwise an older email remains a live way in.
        """
        result = await self._session.execute(
            update(AuthToken)
            .where(
                AuthToken.user_id == user_id,
                AuthToken.purpose == purpose,
                AuthToken.used_at.is_(None),
            )
            .values(used_at=at)
        )
        await self._session.flush()
        return cast("CursorResult[Any]", result).rowcount


class MfaRecoveryCodeRepository:
    """Single-use MFA recovery codes."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_all(
        self, *, user_id: uuid.UUID, code_hashes: Sequence[str]
    ) -> None:
        """Discard any existing codes and store a fresh set.

        Re-enrolling must not leave the previous device's codes usable.
        """
        await self._session.execute(
            delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user_id)
        )
        for code_hash in code_hashes:
            self._session.add(MfaRecoveryCode(user_id=user_id, code_hash=code_hash))
        await self._session.flush()

    async def list_unused(self, *, user_id: uuid.UUID) -> Sequence[MfaRecoveryCode]:
        return (
            await self._session.scalars(
                select(MfaRecoveryCode).where(
                    MfaRecoveryCode.user_id == user_id,
                    MfaRecoveryCode.used_at.is_(None),
                )
            )
        ).all()

    async def mark_used(self, code: MfaRecoveryCode, *, at: datetime) -> None:
        code.used_at = at
        await self._session.flush()
