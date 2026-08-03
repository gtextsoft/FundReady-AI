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
import os
import uuid
from typing import Final

from redis import Redis
from rq import Queue, SimpleWorker, Worker
from rq.worker import BaseWorker

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


_connection: Redis | None = None
"""The one client, built on first use rather than at import.

**Cached deliberately, and the earlier version was wrong to rebuild it.**
`Redis.from_url` constructs a *new connection pool* every call, and `get_queue`
is reached once per enqueue -- so a busy web process created a pool per request
and leaked connections until garbage collection caught up. Against a managed
Redis that caps concurrent connections (Upstash does) that surfaces as
intermittent enqueue failures under load, which is the worst possible shape for
a bug: it looks like the queue is flaky rather than like the client is wrong.

The original reasoning -- "do not hold a connection built at import time" -- was
right and is preserved. This is built lazily on first call, so importing the
module for `RUN_AUDIT_JOB` still costs nothing and `configure_logging` has
already run by the time a socket is opened.
"""


_connection_url: str | None = None
"""Which URL `_connection` was built for.

Keyed rather than a bare singleton so a changed `REDIS_URL` rebuilds the client
instead of being silently ignored. Mostly this matters to tests, which point the
queue at different URLs within one process -- but it is also what stops a
settings reload in production from leaving the old endpoint in place, which
would be invisible until someone wondered why jobs went to the wrong Redis.
"""


def _client(url: str) -> Redis:
    global _connection, _connection_url
    if _connection is None or _connection_url != url:
        _connection_url = url
        _connection = Redis.from_url(
            url,
            # Managed Redis closes idle connections, and RQ's worker sits in a
            # blocking read for minutes at a time. Without a health check the
            # worker discovers the drop as a `ConnectionError` mid-job; with it,
            # redis-py revalidates and reconnects transparently. 30s is well
            # inside the idle timeouts these services use.
            health_check_interval=30,
            socket_keepalive=True,
            # Fail fast rather than hanging a request thread on a queue that is
            # unreachable. The founder gets an error they can retry, which is
            # better than a request that never returns.
            socket_connect_timeout=10,
            retry_on_timeout=True,
        )
    return _connection


def get_queue() -> Queue:
    """The work queue, over a lazily-built shared connection.

    `rediss://` (TLS) works unchanged -- `Redis.from_url` reads the scheme, so
    an Upstash URL needs no special handling here. **Use the Redis-protocol
    connection string, not the REST endpoint**: RQ speaks the wire protocol and
    the REST URL will not connect.
    """
    settings = get_settings()
    if settings.redis_url is None or not settings.redis_url.get_secret_value().strip():
        raise QueueUnavailableError(
            "REDIS_URL is not set, so background jobs cannot be dispatched."
        )
    return Queue(
        settings.queue_name, connection=_client(settings.redis_url.get_secret_value())
    )


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


def _worker_class() -> type[BaseWorker]:
    """`Worker` where the platform can fork, `SimpleWorker` where it cannot.

    **RQ's default worker forks a work horse per job, and `os.fork` does not
    exist on Windows.** The worker starts, claims the first job, and dies with
    `AttributeError: module 'os' has no attribute 'fork'` -- which is why no
    audit had ever been run through the queue on a development machine here,
    and why the transport stayed the untested inch for so long.

    Forking is the right default in production and is kept there: each job runs
    in its own process, so a crash, a leak, or a job that wedges takes the work
    horse with it and leaves the worker listening. `SimpleWorker` runs the job
    in-process and has neither property -- it is a development affordance, not
    a deployment choice.

    Render runs Linux, so production is unaffected by this branch. If that ever
    stops being true, the fix is a container, not this function.
    """
    # A capability check rather than `sys.platform == "win32"`: it says what
    # actually matters, and it does not make the other branch dead code to a
    # type checker that has already decided which platform this is.
    if not hasattr(os, "fork"):
        logger.warning(
            "using SimpleWorker: this platform cannot fork, so jobs run "
            "in-process without the isolation a forking worker gives",
            extra={"context": {"platform": os.name}},
        )
        return SimpleWorker
    return Worker


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
    _worker_class()([queue], connection=queue.connection).work(with_scheduler=False)


if __name__ == "__main__":  # pragma: no cover - process entry point
    main()
