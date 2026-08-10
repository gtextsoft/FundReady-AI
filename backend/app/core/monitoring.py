"""Error reporting (Sentry).

`SENTRY_DSN` has been a setting since T0.3 and nothing read it, which meant a
deployed process reported errors nowhere but its own stdout. This is the one
place that reads it, called from both entry points -- the API's lifespan and the
worker's `main` -- because an audit fails on the worker, not in a request, and a
web-only integration would miss precisely the failures nobody is watching for.

**Off unless a DSN is set.** Development and CI have none, and a monitoring
integration that had to be disabled by hand in tests would eventually be left on
by accident and start shipping test data to a third party.

**Three separate settings keep founder data out of Sentry, and `send_default_pii`
is only one of them.** `CLAUDE.md` section 4 forbids putting bearer tokens,
financial figures, or founder PII in a store outside our control, and each of
these closes a different route by which they would arrive:

* `send_default_pii=False` drops request bodies, headers, and cookies.
* `include_local_variables=False` drops the local variables of every frame in a
  captured stack. **This is the one that matters most here and it is not implied
  by the first.** The SDK defaults it on, and the audit worker's failure path
  (`workers.tasks.run_audit_async`) has a founder's full financial profile bound
  to `snapshot` at the moment it raises -- revenue, costs, cash on hand. Without
  this, the most sensitive object in the platform is attached to every audit
  failure event.
* `before_send=_scrub` runs the same redaction the log formatter does over the
  exception text, because an exception *message* can carry a secret even when no
  local variable does -- a psycopg error quotes the Neon DSN.

What is left -- the exception type, the redacted message, the stack shape, the
transaction name -- is what actually helps.
"""

import logging
from typing import TYPE_CHECKING, Any

from app.core.config import Environment, Settings
from app.core.logging import redact

if TYPE_CHECKING:
    # Type-only: the runtime import of `sentry_sdk` stays inside `init_sentry`,
    # so a missing dependency remains a logged shrug rather than an ImportError
    # at module load.
    from sentry_sdk.types import Event

logger = logging.getLogger(__name__)

__all__ = ["init_sentry"]

# Sampled rather than complete: traces are billed per event and the API's own
# structured logs already carry request timing. This is a floor for spotting a
# pathological endpoint, not an APM deployment.
_TRACES_SAMPLE_RATE = 0.1


def _scrub(event: "Event", _hint: dict[str, Any]) -> "Event":
    """Redact secret-shaped text from an event before it leaves the process.

    The same `redact` the log formatter uses, applied to the two fields that
    carry free text an exception can smuggle a credential into. Deliberately
    the last line of defence rather than the first: `include_local_variables`
    is what keeps the founder's figures out, and this keeps the DSN and the API
    key out of the message that describes why they failed.

    Written against the event dict rather than any SDK internals, so it can be
    tested by handing it a synthetic event -- which is a test of this hook, not
    of sentry-sdk's capture path.
    """
    for value in event.get("exception", {}).get("values", []):
        if isinstance(value, dict) and isinstance(value.get("value"), str):
            value["value"] = redact(value["value"])

    logentry = event.get("logentry")
    if isinstance(logentry, dict) and isinstance(logentry.get("message"), str):
        logentry["message"] = redact(logentry["message"])

    return event


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
        include_local_variables=False,
        before_send=_scrub,
        traces_sample_rate=(
            _TRACES_SAMPLE_RATE if settings.app_env is Environment.PRODUCTION else 0.0
        ),
    )
    sentry_sdk.set_tag("component", component)
    logger.info("error reporting enabled", extra={"context": {"component": component}})
    return True
