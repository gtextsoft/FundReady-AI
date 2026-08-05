"""The evidence upload lifecycle and its limits (T3.5).

Layer: **service** (ARCHITECTURE.md section 3). Pure: enums, constants, and the
one arithmetic rule about attempts. No I/O.

**The upload lifecycle is `intake.documents`', deliberately reused rather than
re-derived.** Evidence is a founder uploading a file, which is a problem already
solved once: a row exists before the object does, the client `PUT`s to a signed
URL, and the server judges what actually arrived rather than what was declared.
`ALLOWED_CONTENT_TYPES` and `MAX_UPLOAD_BYTES` are imported from there for the
same reason -- a second allowlist is a second thing to forget to update, and the
divergence would show up as a format a founder can attach to a deck but not to
evidence, which nobody would think to test.
"""

from enum import StrEnum
from typing import Final

from app.modules.intake.documents import (
    ALLOWED_CONTENT_TYPES,
    MAX_UPLOAD_BYTES,
    is_allowed_content_type,
)

__all__ = [
    "ALLOWED_CONTENT_TYPES",
    "AssessmentOutcome",
    "MAX_ASSESSMENT_ATTEMPTS",
    "MAX_UPLOAD_BYTES",
    "EvidenceStatus",
    "attempts_remaining",
    "is_allowed_content_type",
]


class EvidenceStatus(StrEnum):
    """Where an upload sits, independent of how it was graded.

    Kept separate from `AssessmentOutcome` because they answer different
    questions and fail independently: a file can arrive perfectly and be graded
    `fail`, or be rejected by storage validation and never reach the grader at
    all. Collapsing them into one column would make "rejected" and "failed"
    indistinguishable to a founder, and those mean very different things --
    one is "your file did not upload", the other is "your work was assessed".
    """

    PENDING = "pending"
    """Reserved. The client has a signed URL and has not confirmed the upload."""

    READY = "ready"
    """The object is present, within limits, and of an accepted type."""

    REJECTED = "rejected"
    """The object was missing, empty, oversized, or an unaccepted type. The
    bytes were deleted; the row is kept so the founder gets a reason."""


class AssessmentOutcome(StrEnum):
    """What the grader concluded about one submission.

    Three values rather than a boolean, and the third is the important one:
    `CLAUDE.md` section 5 forbids a confident verdict on thin evidence, so
    "plausible but unproven" needs somewhere to land that is neither a pass nor
    an accusation.

    **Lives here rather than in `assessment.py`** so `models.py` can describe the
    column without importing the AI client. A model layer that pulls in
    `anthropic` to declare an enum has the dependency arrow backwards.
    """

    # noqa on the next line: flake8-bandit reads the name "PASS" as a
    # credential. It is a grading outcome, not a secret.
    PASS = "pass"  # noqa: S105
    """The submission shows the action was done. The criterion is met."""

    FAIL = "fail"
    """The submission does not show this, and more of the same will not help."""

    NEEDS_MORE = "needs_more"
    """Consistent with the action being done, but it does not demonstrate it.
    The default whenever the grader is unsure."""


MAX_ASSESSMENT_ATTEMPTS: Final = 3
"""Graded attempts a founder gets per task before it locks.

**A cap has to exist, and that part is not a preference.** Grading is a model
call, a model does not answer identically twice, and the outcome decides whether
a founder passes a gate into investor visibility -- so unlimited attempts means
a determined founder eventually passes anything. Each attempt is also a billed
`AUDIT`-tier call with no per-user budget cap behind it yet (T5.5).

**The number three is untuned**, the same false-precision problem as
`READY_THRESHOLD` and `PRIORITY_DIMENSIONS`. It is chosen to leave room for the
common honest case -- a first submission graded `needs_more`, corrected once --
without leaving room to grind. Move it when there is evidence, not intuition.

Reaching the cap **locks the task rather than failing it**: `status` stays
whatever the last grading said, and the founder is refused a *new* upload. A
SACI admin reopens it, which resets the counter and is audit-logged. Locking
rather than failing matters because a `fail` is a statement about the work and a
lock is a statement about the process, and conflating them would tell a founder
their business fell short when what actually happened is that they ran out of
tries.
"""


def attempts_remaining(used: int) -> int:
    """How many graded attempts are left. Never negative.

    Clamped rather than allowed to go negative because this number is shown to a
    founder, and "-1 attempts remaining" is not a thing anyone can act on. A
    negative would mean the cap was breached, which the service prevents --
    clamping here keeps a display bug from becoming a second, louder bug.
    """
    return max(0, MAX_ASSESSMENT_ATTEMPTS - used)
