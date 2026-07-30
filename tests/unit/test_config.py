"""Settings behaviour, including the guards that keep secrets out of output."""

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Environment, Settings, SettingsError, get_settings

# Secret-looking values, so a leak into an error message is unmistakable.
PRODUCTION_ENV = {
    "APP_ENV": "production",
    "APP_LINK_BASE_URL": "https://app.fundready.test",
    "DATABASE_URL": "postgresql://user:dbpassword1@host/db",
    "JWT_SECRET_KEY": "jwt-signing-key-value-long-enough-to-pass-32",
    "MFA_SECRET_ENCRYPTION_KEY": "mfa-encryption-key-value",
    "R2_ACCOUNT_ID": "r2-account-id-value",
    "R2_ENDPOINT_URL": "https://r2-account-id-value.r2.cloudflarestorage.com",
    "R2_ACCESS_KEY_ID": "r2-access-key-value",
    "R2_SECRET_ACCESS_KEY": "r2-secret-key-value",
    "R2_BUCKET_DOCUMENTS": "fundready-documents",
    "R2_BUCKET_EVIDENCE": "fundready-evidence",
    "REDIS_URL": "redis://:redispassword1@host:6379",
    "ANTHROPIC_API_KEY": "anthropic-key-value",
    "STRIPE_SECRET_KEY": "stripe-key-value",
    "STRIPE_WEBHOOK_SECRET": "webhook-secret-value",
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
    """Development must run before Neon, R2, Stripe, and Redis exist."""
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


class TestEnvExampleStaysCurrent:
    """`.env.example` is the operator's only inventory of what must be set.

    Settings reject unknown keys, so a stale example file does not merely
    mislead -- copying it produces a service that refuses to start.
    """

    @staticmethod
    def _documented_keys() -> set[str]:
        example = Path(__file__).resolve().parents[2] / ".env.example"
        return {
            line.split("=", 1)[0].strip()
            for line in example.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#") and "=" in line
        }

    def test_no_undocumented_settings(self) -> None:
        fields = {name.upper() for name in Settings.model_fields}

        assert not fields - self._documented_keys(), "add these to .env.example"

    def test_no_stale_keys(self) -> None:
        fields = {name.upper() for name in Settings.model_fields}

        assert not self._documented_keys() - fields, (
            "these keys no longer exist and would stop the service from starting"
        )


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
            "APP_LINK_BASE_URL",
            "JWT_SECRET_KEY",
            "MFA_SECRET_ENCRYPTION_KEY",
            "R2_ACCOUNT_ID",
            "R2_ENDPOINT_URL",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_BUCKET_DOCUMENTS",
            "R2_BUCKET_EVIDENCE",
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

    def test_short_jwt_secret_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A short signing key makes every access token forgeable offline."""
        with pytest.raises(SettingsError, match="at least 32 characters"):
            _load(monkeypatch, _production(JWT_SECRET_KEY="too-short"))

    @pytest.mark.parametrize(
        ("setting", "value", "match"),
        [
            ("ARGON2_MEMORY_COST_KIB", "8192", "ARGON2_MEMORY_COST_KIB"),
            ("ARGON2_TIME_COST", "1", "ARGON2_TIME_COST"),
        ],
    )
    def test_argon2_below_the_owasp_floor_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, setting: str, value: str, match: str
    ) -> None:
        with pytest.raises(SettingsError, match=match):
            _load(monkeypatch, _production(**{setting: value}))

    def test_development_may_run_cheaper_argon2(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test suites would crawl at production cost; production may not."""
        settings = _load(monkeypatch, {"ARGON2_MEMORY_COST_KIB": "8192"})

        assert settings.argon2_memory_cost_kib == 8192
