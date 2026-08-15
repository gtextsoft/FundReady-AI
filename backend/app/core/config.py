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
from typing import Annotated, Any, Final, Literal

from pydantic import BeforeValidator, SecretStr, ValidationError
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


# Security floors enforced in production (AUTH.md sections 3.1, 4.1).
MIN_JWT_SECRET_LENGTH: Final = 32
MIN_ARGON2_MEMORY_COST_KIB: Final = 19456  # OWASP minimum
MIN_ARGON2_TIME_COST: Final = 2


def _is_comment_only(raw: str) -> bool:
    """True when a value is really this key's trailing comment.

    `FOO=  # note` parses as the *value* `# note`, because the key is blank and
    dotenv only strips an inline comment when there is a value in front of it.
    A setting can never legitimately begin with `#`, so treating that as unset
    is safe and catches the whole class rather than one file's formatting.
    """
    return raw.strip().startswith("#")


def _blank_to_none(value: Any) -> Any:
    """Treat an empty -- or comment-only -- environment value as unset.

    `.env.example` ships every key with an empty value, so a copied file would
    otherwise fail to parse on the first optional number it meets -- `FOO=` is
    an empty string, not a missing key.
    """
    if isinstance(value, str) and (not value.strip() or _is_comment_only(value)):
        return None
    return value


def _blank_str(value: Any) -> Any:
    """Same rule as `_blank_to_none`, for settings that default to `""`."""
    return "" if _blank_to_none(value) is None else value


OptionalInt = Annotated[int | None, BeforeValidator(_blank_to_none)]
"""An integer setting that may be left blank in `.env`."""

BlankableStr = Annotated[str, BeforeValidator(_blank_str)]
"""A string setting whose blank form must survive a trailing `.env` comment."""


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
    # Where emailed links point. Owned by the mobile client (deep link or
    # universal link), NOT by this API: mail security scanners prefetch every
    # URL they see, which would consume a single-use token before the user
    # ever clicked it. The client extracts the token and POSTs it back.
    app_link_base_url: str = ""
    # Comma-separated. Parsed by `cors_origins`; kept as a string because
    # pydantic-settings would otherwise try to JSON-decode a list-typed field.
    cors_allowed_origins: str = ""

    # -- Database (Neon: serverless Postgres + pgvector) --------------------
    database_url: SecretStr | None = None
    # Optional: Neon's direct (non-pooled) endpoint. The pooler is PgBouncer in
    # transaction mode, which is right for the app but not the recommended
    # target for DDL. Falls back to `database_url` when unset.
    database_migration_url: SecretStr | None = None
    # Test-only, and never read by the application: a throwaway database (a Neon
    # branch) that the suite may write to. Declared here solely because settings
    # reject unknown keys, and this one legitimately lives in `.env` beside the
    # others -- without a field for it, its presence would stop the service.
    test_database_url: SecretStr | None = None

    # -- Authentication (self-built -- AUTH.md) -----------------------------
    # Signs and verifies our own access tokens. One service does both, so a
    # symmetric key is sufficient; `jwt_key_id` allows rotation and the
    # algorithm is pinned here rather than read from a token header.
    jwt_secret_key: SecretStr | None = None
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_key_id: str = "k1"
    jwt_issuer: str = "fundready"
    jwt_audience: str = "fundready-api"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    # Argon2id cost, tunable per environment because memory cost is real RAM
    # on a small host (AUTH.md section 3.1). Production floors are enforced by
    # `validate_settings`.
    argon2_memory_cost_kib: int = 65536
    argon2_time_cost: int = 3
    argon2_parallelism: int = 1

    # Encrypts TOTP secrets at rest, so a database leak does not defeat MFA.
    mfa_secret_encryption_key: SecretStr | None = None

    # -- Object storage (Cloudflare R2 -- never Postgres) -------------------
    r2_account_id: str = ""
    r2_endpoint_url: str = ""
    r2_access_key_id: SecretStr | None = None
    r2_secret_access_key: SecretStr | None = None
    r2_bucket_documents: str = ""
    r2_bucket_evidence: str = ""
    storage_signed_url_ttl_seconds: int = 900

    # -- Queue --------------------------------------------------------------
    redis_url: SecretStr | None = None
    queue_name: str = "fundready"

    # -- AI -----------------------------------------------------------------
    # Model ids and budget values are chosen in T2.1/T5.5 (DECISIONS.md D16);
    # left unset here so no model choice is smuggled in as a default.
    anthropic_api_key: SecretStr | None = None
    # `BlankableStr`, not `str`: a blank key carrying a trailing comment parses
    # as that comment, and a model id is the one setting where a wrong value
    # fails as a confusing 404 rather than a validation error.
    ai_model_audit: BlankableStr = ""
    ai_model_chat: BlankableStr = ""
    ai_max_output_tokens: OptionalInt = None
    # Enforced in `ai.client` (T5.5). Default caps spend when unset.
    ai_daily_budget_tokens_per_user: OptionalInt = 500_000

    # -- Stripe -------------------------------------------------------------
    stripe_secret_key: SecretStr | None = None
    stripe_webhook_secret: SecretStr | None = None
    stripe_publishable_key: str = ""
    # Recurring Price for the founder monthly subscription (DECISIONS.md D24).
    stripe_price_id_unlock: BlankableStr = ""
    # Optional overrides; blank falls back to APP_LINK_BASE_URL deep links.
    stripe_checkout_success_url: BlankableStr = ""
    stripe_checkout_cancel_url: BlankableStr = ""

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
        """Allowed CORS origins.

        Empty means no cross-origin access in staging/production (correct for a
        mobile-only client). In development, an empty list falls back to the
        local Expo web preview hosts so the browser can reach this API without
        every machine needing a hand-edited `CORS_ALLOWED_ORIGINS`.
        """
        configured = [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]
        if configured:
            return configured
        if self.app_env is Environment.DEVELOPMENT:
            return [
                "http://localhost:8097",
                "http://127.0.0.1:8097",
                "http://localhost:8081",
                "http://127.0.0.1:8081",
                "http://localhost:19006",
                "http://127.0.0.1:19006",
            ]
        return []

    def missing_production_settings(self) -> list[str]:
        """Names of required settings that are absent, for production only.

        **Required means "some code reads it", not "it exists as a field".**
        Stripe keys return here now that `commerce` creates Checkout sessions
        and verifies webhooks (T3.3 / DECISIONS.md D24).
        """
        if not self.is_production:
            return []

        required: dict[str, SecretStr | str | None] = {
            "DATABASE_URL": self.database_url,
            "APP_LINK_BASE_URL": self.app_link_base_url,
            "JWT_SECRET_KEY": self.jwt_secret_key,
            "MFA_SECRET_ENCRYPTION_KEY": self.mfa_secret_encryption_key,
            "R2_ACCOUNT_ID": self.r2_account_id,
            # Required outright rather than derived from the account id: R2 is
            # reached through this URL, and `core.storage` refuses to build a
            # client without it (T1.5). A blank endpoint would sign URLs that
            # point nowhere, which looks like success until an upload vanishes.
            "R2_ENDPOINT_URL": self.r2_endpoint_url,
            "R2_ACCESS_KEY_ID": self.r2_access_key_id,
            "R2_SECRET_ACCESS_KEY": self.r2_secret_access_key,
            "R2_BUCKET_DOCUMENTS": self.r2_bucket_documents,
            "R2_BUCKET_EVIDENCE": self.r2_bucket_evidence,
            "REDIS_URL": self.redis_url,
            "ANTHROPIC_API_KEY": self.anthropic_api_key,
            # Email is required, and its absence is the worst failure mode this
            # check has: nothing else reports it. Registration succeeds, the
            # account sits at `pending_verification`, the verification email is
            # never sent, and the founder can never log in -- with no error
            # anywhere and a deploy that looks healthy. It was missing from this
            # list, so `APP_ENV=production` booted happily into exactly that.
            "RESEND_API_KEY": self.resend_api_key,
            "EMAIL_FROM_ADDRESS": self.email_from_address,
            "STRIPE_SECRET_KEY": self.stripe_secret_key,
            "STRIPE_WEBHOOK_SECRET": self.stripe_webhook_secret,
            "STRIPE_PRICE_ID_UNLOCK": self.stripe_price_id_unlock,
        }
        return sorted(name for name, value in required.items() if _is_blank(value))


def validate_settings(settings: Settings) -> None:
    """Enforce the production requirements, raising only setting *names*.

    Development is allowed to boot half-configured so the app runs before
    Neon, Stripe, and Redis exist. Production is not: a missing secret must
    stop the process rather than surface later as a confusing runtime error.
    """
    if not settings.is_production:
        return

    missing = settings.missing_production_settings()
    if missing:
        raise SettingsError(
            f"missing required settings in production: {', '.join(missing)}"
        )

    # We sign our own tokens now, so key strength is ours to guarantee. A short
    # secret makes every access token forgeable offline.
    key = settings.jwt_secret_key
    if key is not None and len(key.get_secret_value()) < MIN_JWT_SECRET_LENGTH:
        raise SettingsError(
            f"JWT_SECRET_KEY must be at least {MIN_JWT_SECRET_LENGTH} characters"
        )

    # Argon2id floors from OWASP (AUTH.md section 3.1). Development may run
    # cheaper for speed; production may not.
    if settings.argon2_memory_cost_kib < MIN_ARGON2_MEMORY_COST_KIB:
        raise SettingsError(
            f"ARGON2_MEMORY_COST_KIB must be at least {MIN_ARGON2_MEMORY_COST_KIB}"
        )
    if settings.argon2_time_cost < MIN_ARGON2_TIME_COST:
        raise SettingsError(f"ARGON2_TIME_COST must be at least {MIN_ARGON2_TIME_COST}")


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
