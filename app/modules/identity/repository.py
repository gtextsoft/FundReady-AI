"""Identity data access.

Layer: **repository** (ARCHITECTURE.md section 3) -- database access only.
Queries in, models/data out. No business rules, no authorization decisions.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AccountStatus, Role
from app.modules.identity.models import AuditLog, RefreshToken, User


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

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        role: Role,
        status: AccountStatus,
        first_name: str = "",
        last_name: str = "",
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
