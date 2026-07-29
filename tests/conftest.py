"""Shared test fixtures.

Settings are cached process-wide, so any test that touches the environment must
clear the cache on both sides of itself. `isolated_env` does that automatically
for every test.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core import db
from app.core.config import Settings, get_settings

# Environment variables the settings object reads. Cleared before each test so
# a developer's real .env cannot change a test outcome.
_SETTINGS_ENV_VARS = (
    "APP_ENV",
    "LOG_LEVEL",
    "API_BASE_URL",
    "CORS_ALLOWED_ORIGINS",
    "DATABASE_URL",
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_JWKS_URL",
    "SUPABASE_JWT_SECRET",
    "SUPABASE_JWT_AUDIENCE",
    "STORAGE_BUCKET_DOCUMENTS",
    "STORAGE_BUCKET_EVIDENCE",
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
    # Never read the developer's real .env during tests.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
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
