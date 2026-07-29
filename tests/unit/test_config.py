"""Settings behaviour, including the guards that keep secrets out of output."""

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Environment, Settings, SettingsError, get_settings

# Secret-looking values, so a leak into an error message is unmistakable.
PRODUCTION_ENV = {
    "APP_ENV": "production",
    "DATABASE_URL": "postgresql://user:dbpassword1@host/db",
    "SUPABASE_URL": "https://project.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role-key-value",
    "REDIS_URL": "redis://:redispassword1@host:6379",
    "ANTHROPIC_API_KEY": "anthropic-key-value",
    "STRIPE_SECRET_KEY": "stripe-key-value",
    "STRIPE_WEBHOOK_SECRET": "webhook-secret-value",
    "SUPABASE_JWT_SECRET": "jwt-secret-value",
}


def _load(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> Settings:
    """Load settings through the real entry point, from the environment."""
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    return get_settings()


def _production(**overrides: str) -> dict[str, str]:
    """A minimally complete production configuration."""
    return {**PRODUCTION_ENV, **overrides}


def test_defaults_to_development() -> None:
    settings = Settings()

    assert settings.app_env is Environment.DEVELOPMENT
    assert settings.is_production is False


def test_development_boots_without_secrets() -> None:
    """Development must run before Supabase, Stripe, and Redis exist."""
    settings = Settings()

    assert settings.database_url is None
    assert settings.anthropic_api_key is None


def test_cors_origins_parsed_from_csv() -> None:
    settings = Settings(cors_allowed_origins=" https://a.example , https://b.example ")

    assert settings.cors_origins == ["https://a.example", "https://b.example"]


def test_cors_origins_empty_by_default() -> None:
    """No configuration means no cross-origin access, not 'allow everything'."""
    assert Settings().cors_origins == []


def test_secrets_are_not_exposed_by_repr() -> None:
    settings = Settings(database_url=SecretStr("postgresql://user:hunter2@host/db"))

    assert "hunter2" not in repr(settings)
    assert "hunter2" not in str(settings.database_url)
    assert settings.database_url is not None
    assert settings.database_url.get_secret_value().endswith("@host/db")


def test_unknown_setting_is_rejected() -> None:
    """A key nothing claims is a typo or drift -- fail, do not ignore."""
    with pytest.raises(ValidationError):
        Settings(totally_unknown_setting="x")  # type: ignore[call-arg]


class TestProductionGuards:
    def test_complete_production_config_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _load(monkeypatch, _production())

        assert settings.is_production is True

    @pytest.mark.parametrize(
        "missing",
        [
            "DATABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY",
            "REDIS_URL",
            "ANTHROPIC_API_KEY",
            "STRIPE_SECRET_KEY",
            "STRIPE_WEBHOOK_SECRET",
        ],
    )
    def test_missing_required_setting_fails_startup(
        self, monkeypatch: pytest.MonkeyPatch, missing: str
    ) -> None:
        env = _production()
        env.pop(missing)

        with pytest.raises(SettingsError) as exc_info:
            _load(monkeypatch, env)

        assert missing in str(exc_info.value)

    def test_failure_message_names_settings_but_never_values(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A startup failure is printed to logs -- it must not carry secrets."""
        env = _production()
        env.pop("STRIPE_SECRET_KEY")

        with pytest.raises(SettingsError) as exc_info:
            _load(monkeypatch, env)

        message = str(exc_info.value)
        assert "STRIPE_SECRET_KEY" in message
        for value in PRODUCTION_ENV.values():
            if value != "production":
                assert value not in message

    def test_invalid_setting_failure_carries_no_values(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even a pydantic-level failure must not render the settings it saw."""
        env = _production(STORAGE_SIGNED_URL_TTL_SECONDS="not-an-integer")

        with pytest.raises(SettingsError) as exc_info:
            _load(monkeypatch, env)

        message = str(exc_info.value)
        assert "storage_signed_url_ttl_seconds" in message
        assert "not-an-integer" not in message
        for value in PRODUCTION_ENV.values():
            if value != "production":
                assert value not in message

    def test_jwt_verification_method_must_be_unambiguous(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = _production()
        env.pop("SUPABASE_JWT_SECRET")
        with pytest.raises(SettingsError, match="exactly one"):
            _load(monkeypatch, env)

        with pytest.raises(SettingsError, match="exactly one"):
            _load(
                monkeypatch,
                _production(SUPABASE_JWKS_URL="https://project/.well-known/jwks.json"),
            )

    def test_either_verification_method_alone_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        by_secret = _load(monkeypatch, _production())
        assert by_secret.supabase_jwt_secret is not None

        env = _production(SUPABASE_JWKS_URL="https://project/.well-known/jwks.json")
        env.pop("SUPABASE_JWT_SECRET")
        monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
        by_jwks = _load(monkeypatch, env)

        assert by_jwks.supabase_jwks_url.endswith("jwks.json")
