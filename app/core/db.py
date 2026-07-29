"""Database engine, session, and declarative base.

Async SQLAlchemy 2.0 over psycopg 3, against Neon. The workload is dominated by
waiting on I/O -- Claude, Stripe, the database -- which is where async pays.

Connections use a least-privilege role. Tenant isolation is enforced **in the
service layer** (DECISIONS.md D13); Postgres RLS is an optional second wall, and
where it is used the caller is passed per transaction with
`SET LOCAL app.current_user_id` -- never plain `SET`, which would leak one
user's identity into another request over a pooled connection.

Schema changes only ever happen through Alembic migrations
(ARCHITECTURE.md section 6) -- `Base.metadata.create_all` is never called.
"""

from collections.abc import AsyncIterator
from typing import Final

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError

# Predictable constraint names, so Alembic autogenerate produces stable
# migrations instead of database-assigned names that differ per environment.
NAMING_CONVENTION: Final[dict[str, str]] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every ORM model in the application."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def resolve_database_url(
    settings: Settings | None = None, *, for_migrations: bool = False
) -> str:
    """Resolve the connection URL and force the psycopg dialect.

    Accepts the plain `postgresql://` form Neon hands out and rewrites it to
    `postgresql+psycopg://`, so operators are not required to know the driver
    suffix. The same dialect serves both modes -- `create_async_engine` runs it
    async, `create_engine` runs it sync.

    `for_migrations` prefers `DATABASE_MIGRATION_URL` (Neon's direct endpoint)
    and falls back to `DATABASE_URL`. DDL through a transaction-mode pooler is
    not what the pooler is for.
    """
    settings = settings or get_settings()

    secret = settings.database_url
    if for_migrations and settings.database_migration_url is not None:
        secret = settings.database_migration_url
    if secret is None:
        raise ConfigurationError

    url = secret.get_secret_value().strip()
    if not url:
        raise ConfigurationError

    dialect = "postgresql+psycopg://"
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return dialect + url[len(prefix) :]
    return url


def get_engine() -> AsyncEngine:
    """The process-wide engine, created on first use.

    Lazy so the app boots in development before a database exists; a request
    that actually needs the database then fails cleanly.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            resolve_database_url(),
            pool_pre_ping=True,  # Neon scales to zero; revive stale connections
            echo=False,  # never log SQL: statements carry PII and financials
            connect_args={
                # Neon's pooled endpoint is PgBouncer in transaction mode, where
                # psycopg's automatic server-side prepared statements can fail
                # intermittently once a connection is reused. Disabling them
                # costs little and removes the whole failure class.
                "prepare_threshold": None,
            },
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a transactional session.

    Commits when the handler returns, rolls back on any exception. A handler
    never has to remember to do either.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Close pooled connections on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def reset_engine_cache() -> None:
    """Drop the cached engine without awaiting disposal. For tests only."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None


__all__ = [
    "AsyncSession",
    "Base",
    "dispose_engine",
    "get_engine",
    "get_session",
    "get_session_factory",
    "resolve_database_url",
    "reset_engine_cache",
]
