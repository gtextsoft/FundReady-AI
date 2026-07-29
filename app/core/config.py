"""Environment-driven settings.

All configuration and every secret comes from the environment or the secret
manager -- never hardcoded, never committed, never logged (CLAUDE.md section 4).
`.env.example` lists every key this module reads and must stay current.

Two deliberate choices:

* Secrets are typed `SecretStr`, so a stray `repr()`, log line, or traceback
  prints `**********` instead of the value.
* `extra="forbid"` means a key in `.env` that no field claims is a startup
  error. Silent drift between `.env` and this file is how a rotated secret ends
  up ignored.
"""

from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsError(RuntimeError):
    """Configuration is invalid or incomplete.

    Raised instead of letting a pydantic `ValidationError` escape, because that
    exception renders the values it validated -- which here are secrets.
    """


class Environment(StrEnum):
    """Deployment environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


def _is_blank(value: SecretStr | str | None) -> bool:
    """True when a setting is unset or empty, without unwrapping into a log."""
    if value is None:
        return True
    raw = value.get_secret_value() if isinstance(value, SecretStr) else value
    return not raw.strip()


class Settings(BaseSettings):
    """Application settings, read once from the environment at startup."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
    )

    # -- Application --------------------------------------------------------
    app_env: Environment = Environment.DEVELOPMENT
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_base_url: str = ""
    # Comma-separated. Parsed by `cors_origins`; kept as a string because
    # pydantic-settings would otherwise try to JSON-decode a list-typed field.
    cors_allowed_origins: str = ""

    # -- Database -----------------------------------------------------------
    database_url: SecretStr | None = None

    # -- Supabase (auth + storage) -----------------------------------------
    supabase_url: str = ""
    supabase_anon_key: SecretStr | None = None
    # SERVER-ONLY: bypasses row-level security (AUTH.md section 10).
    supabase_service_role_key: SecretStr | None = None
    # Exactly one of these is used, depending on the project's signing method
    # (AUTH.md section 3 -- open item, confirmed before T0.4).
    supabase_jwks_url: str = ""
    supabase_jwt_secret: SecretStr | None = None
    supabase_jwt_audience: str = "authenticated"

    # -- Object storage -----------------------------------------------------
    storage_bucket_documents: str = ""
    storage_bucket_evidence: str = ""
    storage_signed_url_ttl_seconds: int = 900

    # -- Queue --------------------------------------------------------------
    redis_url: SecretStr | None = None
    queue_name: str = "fundready"

    # -- AI -----------------------------------------------------------------
    # Model ids and budget values are chosen in T2.1/T5.5 (DECISIONS.md D16);
    # left unset here so no model choice is smuggled in as a default.
    anthropic_api_key: SecretStr | None = None
    ai_model_audit: str = ""
    ai_model_chat: str = ""
    ai_max_output_tokens: int | None = None
    ai_daily_budget_tokens_per_user: int | None = None

    # -- Stripe -------------------------------------------------------------
    stripe_secret_key: SecretStr | None = None
    stripe_webhook_secret: SecretStr | None = None
    stripe_publishable_key: str = ""

    # -- Email --------------------------------------------------------------
    resend_api_key: SecretStr | None = None
    email_from_address: str = ""

    # -- Monitoring ---------------------------------------------------------
    sentry_dsn: SecretStr | None = None

    @property
    def is_production(self) -> bool:
        return self.app_env is Environment.PRODUCTION

    @property
    def cors_origins(self) -> list[str]:
        """Allowed CORS origins. Empty means no cross-origin access."""
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    def missing_production_settings(self) -> list[str]:
        """Names of required settings that are absent, for production only."""
        if not self.is_production:
            return []

        required: dict[str, SecretStr | str | None] = {
            "DATABASE_URL": self.database_url,
            "SUPABASE_URL": self.supabase_url,
            "SUPABASE_SERVICE_ROLE_KEY": self.supabase_service_role_key,
            "REDIS_URL": self.redis_url,
            "ANTHROPIC_API_KEY": self.anthropic_api_key,
            "STRIPE_SECRET_KEY": self.stripe_secret_key,
            "STRIPE_WEBHOOK_SECRET": self.stripe_webhook_secret,
        }
        return sorted(name for name, value in required.items() if _is_blank(value))

    def has_unambiguous_jwt_verification(self) -> bool:
        """True when exactly one JWT verification method is configured.

        Neither configured means every authenticated request fails; both
        configured means an ambiguous verification path (AUTH.md section 3).
        """
        jwks = not _is_blank(self.supabase_jwks_url)
        secret = not _is_blank(self.supabase_jwt_secret)
        return jwks != secret


def validate_settings(settings: Settings) -> None:
    """Enforce the production requirements, raising only setting *names*.

    Development is allowed to boot half-configured so the app runs before
    Supabase, Stripe, and Redis exist. Production is not: a missing secret must
    stop the process rather than surface later as a confusing runtime error.
    """
    if not settings.is_production:
        return

    missing = settings.missing_production_settings()
    if missing:
        raise SettingsError(
            f"missing required settings in production: {', '.join(missing)}"
        )

    if not settings.has_unambiguous_jwt_verification():
        raise SettingsError(
            "set exactly one of SUPABASE_JWKS_URL or SUPABASE_JWT_SECRET "
            "to match the project's JWT signing method"
        )


def _describe_without_values(error: ValidationError) -> str:
    """Summarise a settings validation failure using field names only.

    pydantic renders the offending *input* in `ValidationError`, and the input
    here is the settings object -- every secret the process holds. Printed at
    startup that lands in the platform's logs in plaintext, so the exception is
    never allowed to escape: only locations and error types are reported.
    """
    problems = sorted(
        {
            f"{'.'.join(str(part) for part in item['loc']) or '<root>'} "
            f"({item['type']})"
            for item in error.errors()
        }
    )
    return f"invalid settings: {', '.join(problems)}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, loaded once.

    Cached so the environment is read a single time. Tests that change the
    environment must call `get_settings.cache_clear()`.
    """
    try:
        settings = Settings()
    except ValidationError as error:
        # `from None` so the original exception -- which carries the values --
        # is not chained into the traceback.
        raise SettingsError(_describe_without_values(error)) from None

    validate_settings(settings)
    return settings
