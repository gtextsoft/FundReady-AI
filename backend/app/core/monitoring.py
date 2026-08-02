"""Error reporting (Sentry).

`SENTRY_DSN` has been a setting since T0.3 and nothing read it, which meant a
deployed process reported errors nowhere but its own stdout. This is the one
place that reads it, called from both entry points -- the API's lifespan and the
worker's `main` -- because an audit fails on the worker, not in a request, and a
web-only integration would miss precisely the failures nobody is watching for.

**Off unless a DSN is set.** Development and CI have none, and a monitoring
integration that had to be disabled by hand in tests would eventually be left on
by accident and start shipping test data to a third party.

**`send_default_pii` stays off.** Sentry can attach request bodies, headers, and
cookies to an event; here those carry bearer tokens, financial figures, and
founder PII, and `CLAUDE.md` section 4 forbids putting any of them in a store
outside our control. What is left -- the exception, the stack, the transaction
name -- is what actually helps.
"""

import logging

from app.core.config import Environment, Settings

logger = logging.getLogger(__name__)

__all__ = ["init_sentry"]

# Sampled rather than complete: traces are billed per event and the API's own
# structured logs already carry request timing. This is a floor for spotting a
# pathological endpoint, not an APM deployment.
_TRACES_SAMPLE_RATE = 0.1


def init_sentry(settings: Settings, *, component: str) -> bool:
    """Start Sentry if a DSN is configured. Returns whether it was started.

    `component` separates the API's events from the worker's, which otherwise
    arrive in one stream with no way to tell a failed request from a failed
    audit.

    A missing `sentry-sdk` is logged and shrugged off rather than raised: it is
    a declared dependency, so its absence means a broken install, and taking the
    whole process down over the *reporting* of errors would turn a monitoring
    gap into an outage.
    """
    dsn = settings.sentry_dsn.get_secret_value().strip() if settings.sentry_dsn else ""
    if not dsn:
        logger.info(
            "error reporting disabled", extra={"context": {"component": component}}
        )
        return False

    try:
        import sentry_sdk
    except ImportError:  # pragma: no cover - dependency is declared
        logger.warning(
            "sentry-sdk is not installed; error reporting is off",
            extra={"context": {"component": component}},
        )
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.app_env.value,
        send_default_pii=False,
        traces_sample_rate=(
            _TRACES_SAMPLE_RATE if settings.app_env is Environment.PRODUCTION else 0.0
        ),
    )
    sentry_sdk.set_tag("component", component)
    logger.info("error reporting enabled", extra={"context": {"component": component}})
    return True
