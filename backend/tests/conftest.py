"""Shared test fixtures.

Settings are cached process-wide, so any test that touches the environment must
clear the cache on both sides of itself. `isolated_env` does that automatically
for every test.
"""

import asyncio
import os
import re
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import db
from app.core.config import Settings, get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]

# Disabled at import time, not inside a fixture: test modules import
# `app.main` at module scope, which reads settings before any fixture runs.
# Without this, a developer's real .env could decide whether tests pass.
Settings.model_config["env_file"] = None

if sys.platform == "win32":
    # psycopg's async mode cannot run on Windows' default ProactorEventLoop.
    # Mirrors the guard in app/main.py so database-backed tests work here too.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Environment variables the settings object reads. Cleared before each test so
# a developer's real .env cannot change a test outcome.
_SETTINGS_ENV_VARS = (
    "APP_ENV",
    "LOG_LEVEL",
    "API_BASE_URL",
    "APP_LINK_BASE_URL",
    "CORS_ALLOWED_ORIGINS",
    "DATABASE_URL",
    "JWT_SECRET_KEY",
    "JWT_ALGORITHM",
    "JWT_KEY_ID",
    "JWT_ISSUER",
    "JWT_AUDIENCE",
    "ACCESS_TOKEN_TTL_MINUTES",
    "REFRESH_TOKEN_TTL_DAYS",
    "ARGON2_MEMORY_COST_KIB",
    "ARGON2_TIME_COST",
    "ARGON2_PARALLELISM",
    "MFA_SECRET_ENCRYPTION_KEY",
    "R2_ACCOUNT_ID",
    "R2_ENDPOINT_URL",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_DOCUMENTS",
    "R2_BUCKET_EVIDENCE",
    "STORAGE_SIGNED_URL_TTL_SECONDS",
    "REDIS_URL",
    "QUEUE_NAME",
    "ANTHROPIC_API_KEY",
    "AI_MODEL_AUDIT",
    "AI_MODEL_CHAT",
    "AI_MAX_OUTPUT_TOKENS",
    "AI_DAILY_BUDGET_TOKENS_PER_USER",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PUBLISHABLE_KEY",
    "RESEND_API_KEY",
    "EMAIL_FROM_ADDRESS",
    "SENTRY_DSN",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give each test a clean environment and a fresh settings cache."""
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    db.reset_engine_cache()
    yield
    get_settings.cache_clear()
    db.reset_engine_cache()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A client against the real application, exception handlers included."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Database-backed tests
# ---------------------------------------------------------------------------
#
# `isolated_env` deliberately hides the developer's .env from the application,
# so the connection string has to be read here, explicitly and once, before any
# test runs. Parsed by hand rather than through a library so this file adds no
# dependency of its own.
#
# `TEST_DATABASE_URL` should point at a throwaway database -- a Neon branch is
# ideal. It falls back to `DATABASE_URL`, which is safe because every session
# below is rolled back: a database test can never leave a row behind.


def _strip_inline_comment(value: str) -> str:
    """Drop a trailing `# ...` comment from an unquoted value.

    The leading whitespace in the pattern is load-bearing: `#` is a legal
    character inside a Postgres password, and `DATABASE_URL` is read through
    this same parser. Only a `#` that follows whitespace starts a comment.
    """
    match = re.search(r"\s#", value)
    return (value[: match.start()] if match else value).strip()


def _read_env_file(name: str) -> str | None:
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() != name:
            continue
        value = value.strip()
        # A quoted value is taken verbatim -- a `#` inside quotes is content,
        # not a comment. Only unquoted values are comment-stripped.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            return value[1:-1] or None
        return _strip_inline_comment(value).strip() or None
    return None


def _resolve_test_database_url() -> str | None:
    for name in ("TEST_DATABASE_URL", "DATABASE_URL"):
        value = os.environ.get(name) or _read_env_file(name)
        if value:
            for prefix in ("postgresql://", "postgres://"):
                if value.startswith(prefix):
                    return "postgresql+psycopg://" + value[len(prefix) :]
            return value
    return None


TEST_DATABASE_URL = _resolve_test_database_url()

requires_database = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="no TEST_DATABASE_URL or DATABASE_URL configured",
)


# ---------------------------------------------------------------------------
# Live-API tests
# ---------------------------------------------------------------------------
#
# Read here for the same reason as the database URL: `isolated_env` hides the
# developer's .env from the application, so a test that genuinely needs the
# real key has to resolve it explicitly. Mocked transports cannot prove that a
# request shape is one the API accepts -- only a live call can.


def _resolve_anthropic_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or _read_env_file("ANTHROPIC_API_KEY")


ANTHROPIC_API_KEY = _resolve_anthropic_key()

requires_anthropic_key = pytest.mark.skipif(
    ANTHROPIC_API_KEY is None,
    reason="no ANTHROPIC_API_KEY configured",
)


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is always rolled back.

    Nothing a test writes survives it -- which is what makes running against a
    real database acceptable, and is the only way to test a table that refuses
    DELETE and TRUNCATE.
    """
    assert TEST_DATABASE_URL is not None
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        connect_args={"prepare_threshold": None},
    )
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            # Without this, a `commit()` inside the code under test would commit
            # the *outer* transaction and the rollback below would have nothing
            # left to undo -- test rows would survive. Joining as a savepoint
            # keeps those commits real to the code while still discardable.
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()
