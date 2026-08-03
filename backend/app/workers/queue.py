"""Queue setup (Redis + RQ).

Entry point for the worker process:

    python -m app.workers.queue

**Nothing here imports `app.workers.tasks`, and that is deliberate.** Jobs are
enqueued by dotted path (`"app.workers.tasks.run_audit"`), which RQ resolves in
the worker process. The alternative -- importing the handler to pass the
function object -- would make `audit.service` import `workers.tasks`, which
imports `audit.pipeline`, which imports `audit.service`: a genuine import cycle.
The string keeps the web process ignorant of the handlers it queues.

**A blank `REDIS_URL` is a configuration error, not a silent no-op.** Audits run
off this queue (D14), so a web process that accepted submissions and dropped
them would leave founders polling a run that no worker will ever pick up. The
queue is therefore resolved lazily and raises when it is missing, so the failure
lands at the point of enqueue with a message that names the cause.
"""

import logging
import uuid
from typing import Final

from redis import Redis
from rq import Queue, Worker

from app.core.config import get_settings

logger = logging.getLogger(__name__)

__all__ = ["AUDIT_JOB_TIMEOUT", "RUN_AUDIT_JOB", "enqueue_audit", "get_queue", "main"]

RUN_AUDIT_JOB: Final = "app.workers.tasks.run_audit"
"""Dotted path RQ resolves in the worker. See the module docstring."""

AUDIT_JOB_TIMEOUT: Final = 900
"""Seconds before RQ considers an audit job dead.

Fifteen minutes, which is generous on purpose: an audit is one or two calls to
`claude-opus-5` at high effort against a 16k output budget, and a job killed
mid-call is billed in full for an answer nobody receives. The database
constraint, not this timeout, is what stops a retry duplicating the run.
"""


class QueueUnavailableError(RuntimeError):
    """`REDIS_URL` is not configured, so no job can be dispatched."""


def get_queue() -> Queue:
    """The work queue, resolved from settings on each call.

    Not cached: `get_settings` already is, and holding a module-level connection
    would be built at import time -- before `configure_logging`, and in every
    process that merely imports this module for the constants above.
    """
    settings = get_settings()
    if settings.redis_url is None or not settings.redis_url.get_secret_value().strip():
        raise QueueUnavailableError(
            "REDIS_URL is not set, so background jobs cannot be dispatched."
        )
    connection = Redis.from_url(settings.redis_url.get_secret_value())
    return Queue(settings.queue_name, connection=connection)


def enqueue_audit(run_id: uuid.UUID) -> None:
    """Dispatch one audit run to the worker.

    The AuditRun row is created and committed by the caller before this is
    reached, so the job carries only the id: a job argument is a copy taken at
    enqueue time, and the row is the single source of truth for what the run is
    and whether it has already been done.

    `job_id` is the run id, which makes RQ refuse a second in-flight job for the
    same run. That is a convenience, not the guarantee -- an RQ job id is
    released the moment the job finishes, after which only
    `uq_audit_runs_idempotency` still says no.
    """
    get_queue().enqueue(
        RUN_AUDIT_JOB,
        str(run_id),
        job_id=str(run_id),
        job_timeout=AUDIT_JOB_TIMEOUT,
    )


def main() -> None:
    """Run a worker until it is stopped. The container's start command."""
    from app.core.logging import configure_logging
    from app.core.monitoring import init_sentry

    settings = get_settings()
    configure_logging(settings)
    init_sentry(settings, component="worker")

    queue = get_queue()
    logger.info(
        "worker starting",
        extra={
            "context": {
                "queue": settings.queue_name,
                "environment": settings.app_env,
            }
        },
    )
    Worker([queue], connection=queue.connection).work(with_scheduler=False)


if __name__ == "__main__":  # pragma: no cover - process entry point
    main()
