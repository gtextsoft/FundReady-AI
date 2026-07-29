"""Shared test fixtures.

Settings are cached process-wide, so any test that touches the environment must
clear the cache on both sides of itself. `isolated_env` does that automatically
for every test.
"""

import asyncio
import sys
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core import db
from app.core.config import Settings, get_settings

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
