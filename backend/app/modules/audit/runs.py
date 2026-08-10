"""Audit run domain types: lifecycle status and the idempotency fingerprint.

Layer: **domain** (ARCHITECTURE.md section 3). Pure -- no I/O, no ORM import,
so `models.py` can import it without a cycle and the fingerprint can be tested
without a database. Mirrors `intake/documents.py`, which holds the document
enums for the same reason.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Final

__all__ = [
    "LEASE_SECONDS",
    "AuditStatus",
    "input_fingerprint",
    "lease_cutoff",
]

LEASE_SECONDS: Final = 1800
"""How long a worker's claim on a run is honoured before another may take it.

**Twice `workers.queue.AUDIT_JOB_TIMEOUT` (900s), and the margin is the point.**
RQ kills the job at its own timeout and releases the `job_id`, but nothing
writes to the row -- so a run whose worker was killed, or whose container was
redeployed mid-call, stays `RUNNING` with `completed_at` NULL forever. Every
resubmission then returns it with `200` and queues nothing, and `CLIENTS.md`
section 5a tells the client `running` means keep polling, so the mobile app
polls for ever.

A lease shorter than the job timeout would be worse than none: it would let a
second worker claim a run whose first worker is still mid-call, and bill the
platform's most expensive request twice for one verdict. The cost of being
generous here is a founder waiting up to half an hour for a stranded run to
become retryable; the cost of being tight is a double charge.
"""


def lease_cutoff(now: datetime | None = None) -> datetime:
    """The `started_at` before which a `RUNNING` claim is considered abandoned.

    A function of the clock rather than a stored expiry column: an expiry
    written at claim time would need a migration and would still be wrong after
    any change to `LEASE_SECONDS`, because the rows already written would carry
    the old one.
    """
    return (now or datetime.now(UTC)) - timedelta(seconds=LEASE_SECONDS)


class AuditStatus(StrEnum):
    """Where one audit run has got to.

    Documented for clients in `CLIENTS.md`: the mobile app polls this and needs
    to know which values are terminal. `SUCCEEDED` and `FAILED` are; the other
    two mean "keep polling".
    """

    QUEUED = "queued"
    """Accepted and enqueued. No AI spend has happened yet."""

    RUNNING = "running"
    """A worker has picked it up. May be part-way through a billed call."""

    SUCCEEDED = "succeeded"
    """Terminal. A report exists."""

    FAILED = "failed"
    """Terminal for this attempt. Carries a founder-safe reason; the run may be
    retried, which reuses this same row rather than creating a second one."""


def input_fingerprint(
    *,
    profile_fields: Mapping[str, Any],
    document_keys: Sequence[str] = (),
    rubric_version: str,
) -> str:
    """A stable hex digest of everything that can change an audit's outcome.

    This is the idempotency key (DECISIONS.md D14). Two submissions of the same
    profile against the same rubric must not produce two AuditRuns, two bills,
    or two different verdicts -- so the same inputs must hash identically across
    processes and across restarts.

    Three things that make it stable, each of which is a real failure if missed:

    * **`sort_keys`** -- Python dict order follows insertion, so the same
      profile assembled by a different code path would otherwise hash
      differently and re-run a paid audit for nothing.
    * **`default=str`** -- `Decimal` and `datetime` are not JSON-serialisable,
      and coercing money to `float` would let two distinct amounts collide.

    **`profile_fields` must always be the persisted JSONB, never an in-memory
    profile that has not been through the database.** `startup_profiles.fields`
    round-trips through JSONB, so a value written as `Decimal("42.5000")` reads
    back as `42.5`. Those two hash differently, which would bill a founder twice
    for one audit -- the exact failure D14 exists to prevent. `default=str`
    makes that mismatch silent rather than loud, so the discipline is here in
    one code path rather than in a type check: callers pass `profile.fields`
    after a load, and nothing else.
    * **`rubric_version`** -- D12. A new rubric is a genuinely different audit
      of identical data and *must* produce a new run, not reuse the old verdict.

    `document_keys` is empty until T2.4a wires storage in, but it is a parameter
    now rather than later: once documents feed the audit, uploading one has to
    change the fingerprint or the founder's re-audit would silently return the
    pre-upload verdict. Storage keys are used rather than file bytes because a
    key is already unique per upload and hashing the bytes would mean fetching
    every document just to decide whether to skip the work.
    """
    canonical = json.dumps(
        {
            "profile": profile_fields,
            "documents": sorted(document_keys),
            "rubric": rubric_version,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
