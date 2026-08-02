"""The queue's configuration boundary (T2.8).

Two things worth pinning, both of which only bite at deploy time.

**A blank `REDIS_URL` fails loudly.** It is the state the repository has been in
all along, and the tempting behaviour -- treat a missing queue as "no background
work configured" and carry on -- would leave founders polling a run that no
worker will ever claim. `CLAUDE.md` section 5 puts audits on the queue, so no
queue means no audit, and that should be an error at the point of dispatch.

**The job is referenced by dotted path, not by importing the handler.** That is
what keeps the import graph acyclic: `audit.service` needs to enqueue, and the
handler imports `audit.pipeline`, which imports `audit.service`. The string is
load-bearing, so it is asserted to still resolve to a real function.
"""

import importlib
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.workers import queue


@pytest.fixture
def blank_redis(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("REDIS_URL", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_a_blank_redis_url_refuses_rather_than_dropping_the_job(
    blank_redis: None,
) -> None:
    """Accepting a submission nothing will run is worse than refusing it."""
    with pytest.raises(queue.QueueUnavailableError, match="REDIS_URL"):
        queue.get_queue()


def test_dispatch_fails_the_same_way(blank_redis: None) -> None:
    with pytest.raises(queue.QueueUnavailableError):
        queue.enqueue_audit(uuid.uuid4())


def test_the_job_reference_resolves_to_a_real_handler() -> None:
    """RQ resolves this string in the worker process; a typo is invisible here."""
    module_path, _, function_name = queue.RUN_AUDIT_JOB.rpartition(".")
    module = importlib.import_module(module_path)

    assert callable(getattr(module, function_name))


def test_the_queue_module_does_not_import_the_handlers() -> None:
    """The cycle this string exists to avoid.

    `workers.tasks` imports `audit.pipeline`, which imports `audit.service`,
    which enqueues. If `workers.queue` imported `workers.tasks`, that closes
    into a genuine import cycle.
    """
    assert queue.__file__ is not None
    text = Path(queue.__file__).read_text(encoding="utf-8")

    assert "from app.workers.tasks import" not in text
    assert "import app.workers.tasks" not in text


def test_the_job_timeout_leaves_room_for_a_full_audit() -> None:
    """A job killed mid-call is billed in full for an answer nobody receives."""
    assert queue.AUDIT_JOB_TIMEOUT >= 600
