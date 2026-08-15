"""Readiness ORM tables.

Layer: **models** (ARCHITECTURE.md section 3) -- SQLAlchemy table definitions
only. Every schema change also requires an Alembic migration under
`migrations/`; the database is never hand-edited.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.audit.rubric.v1 import Dimension
from app.modules.readiness.evidence import (
    AssessmentOutcome,
    EvidenceStatus,
    attempts_remaining,
)
from app.modules.readiness.generation import Requirement, TaskStatus


class ReadinessTask(Base):
    """One thing a founder must or should do before becoming investor-visible (T3.1).

    Generated from an audit's action plan, never typed by hand and never created
    by the founder: a task exists because the rubric found a gap, and a
    self-declared task would be a claim with no audit behind it.

    **The unique constraint is what makes a re-audit safe.** Every audit rewrites
    its whole action plan, so without a content-derived key the second audit
    would mint a fresh copy of every task and discard the founder's progress on
    all of them -- weeks of evidence stranded on rows nothing points at. Keying
    on **startup + action fingerprint** means the second audit *finds* the
    existing row and updates its severity in place. This is the same reasoning as
    `uq_audit_runs_idempotency`, one layer up: the fingerprint is over the gap
    rather than over the inputs.

    The `dimension` is folded into the fingerprint rather than added to the
    constraint, so the same sentence raised under two dimensions is two tasks --
    see `generation.action_fingerprint` for why that is correct.

    **`status` is never advanced by the client.** `DECISIONS.md` D10 is explicit
    that readiness is earned by doing the work, uploading evidence, and having
    the AI assess it -- not by asserting completion and not by paying. So there
    is no route that takes a status: the column moves off `open` only when
    evidence assessment (T3.5) writes to it. A founder-settable status would let
    anyone clear the investor-visibility gate by tapping a button eleven times.

    **`product_id` is optional.** T3.2 created the catalogue; a task may point
    at a programme that closes its gap. The column is nullable because most
    gaps have no listed product, and `ON DELETE SET NULL` so retiring a
    catalogue item does not delete the founder's task.
    """

    __tablename__ = "readiness_tasks"
    __table_args__ = (
        UniqueConstraint(
            "startup_id", "action_fingerprint", name="uq_readiness_tasks_action"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    startup_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("startup_profiles.id", ondelete="CASCADE"), index=True
    )
    # Denormalised from the profile so `owned_or_404` is a column comparison
    # rather than a join, exactly as `audit_runs` and `documents` do. The
    # authorisation wall is the check itself (CLAUDE.md section 4); this only
    # keeps it cheap enough that nobody is tempted to skip it.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # The run that **most recently** raised this gap, refreshed on regeneration.
    # A task is a live instruction and the client's "why am I being asked this"
    # link has to reach the report that is currently asking; `created_at` is what
    # records when it first appeared. Nullable with `SET NULL` because a deleted
    # run must not take a founder's task history with it -- the work happened
    # whether or not the run that prompted it still exists.
    audit_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="SET NULL"), index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), index=True
    )

    dimension: Mapped[Dimension] = mapped_column(
        SAEnum(
            Dimension,
            native_enum=False,
            length=32,
            name="rubric_dimension",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        index=True,
    )

    # The rubric's own wording, stored as issued. A task a founder disputes has
    # to be readable exactly as it was given to them, for the same reason
    # `AuditRun.report` is stored whole.
    action: Mapped[str] = mapped_column(String(1000))
    action_fingerprint: Mapped[str] = mapped_column(String(64), index=True)

    requirement: Mapped[Requirement] = mapped_column(
        SAEnum(
            Requirement,
            native_enum=False,
            length=16,
            name="task_requirement",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        index=True,
    )
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(
            TaskStatus,
            native_enum=False,
            length=16,
            name="task_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=TaskStatus.OPEN,
        server_default=TaskStatus.OPEN.value,
        index=True,
    )

    # The dimension score that produced this task, or NULL when the dimension
    # was unscoreable. Carried so the client can order and explain without
    # re-reading the report; not shown to the founder as a grade.
    dimension_score: Mapped[int | None] = mapped_column(Integer)

    assessment_attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    """How many times evidence for this task has been **graded** (T3.5).

    The cap that stops the investor-visibility gate being brute-forced. Every
    grading is a fresh shot at a model that will not answer identically twice,
    so unlimited attempts means something eventually passes -- and each attempt
    is a billed `AUDIT`-tier call with no per-user budget cap behind it yet
    (T5.5). `MAX_ASSESSMENT_ATTEMPTS` is the ceiling.

    **Counts gradings, not uploads.** An upload that never completed, or one
    rejected by storage validation before it reached the model, costs nothing
    and consumes nothing. An assessment that returned `needs_more` *does*
    consume one: it was a real call and a real shot at the grader.

    Reset only by an admin reopening the task, which is audit-logged. A founder
    cannot reset it, because a counter the counted party controls is not a cap.
    """

    is_priority: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    """Whether this is in the short list the founder is shown first.

    Mirrors `synthesis.ActionItem.is_priority` and is refreshed on every
    regeneration, because a dimension that improved should stop being a
    priority. See that field for why the plan is marked rather than truncated.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    @property
    def attempts_remaining(self) -> int:
        """Graded attempts left before this task locks.

        A property rather than a column: it is `MAX_ASSESSMENT_ATTEMPTS` minus a
        stored count, and storing a derived number is how the two drift when the
        cap moves. The response schema reads it through `from_attributes`.
        """
        return attempts_remaining(self.assessment_attempts)

    def __repr__(self) -> str:
        return (
            f"<ReadinessTask {self.id} {self.requirement}/{self.status} "
            f"{self.dimension} startup={self.startup_id}>"
        )


class Evidence(Base):
    """One file a founder uploaded to show a readiness task was done (T3.5).

    The **bytes live in R2, never here**, in the `evidence` bucket rather than
    `documents` -- separate from the start because the two have different
    readers and different lifecycles (`core.storage.bucket_name`). This row is
    the metadata, the permission record, and the graded verdict.

    A row exists **before** the file does, exactly as `intake.Document` does:
    create it `pending`, hand the client a signed URL, and only mark it `ready`
    once the object is confirmed present and acceptable. A row stuck at
    `pending` means the client never finished, which is ordinary.

    `owner_id` is denormalised so `core.ownership.owned_or_404` decides access
    here with the same call it uses everywhere else (D13), rather than a bespoke
    rule that loads the task and then the profile.

    **The verdict is stored, not recomputed.** `outcome` and `reasons` are what
    the grader said at the time it said it, kept because a founder who disputes
    a `fail` is entitled to the assessment exactly as issued -- the same reason
    `AuditRun.report` is stored whole. `assessment_prompt_ref` records which
    prompt version produced it (D12), so a grading stays explainable after the
    prompt moves on.

    **Nothing here is served to an investor.** Evidence is a founder's working
    material about their own gaps; discovery serves `investor.StartupCard` and
    only a SACI reveal goes further (D8).
    """

    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("readiness_tasks.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Denormalised from the task so a startup-wide evidence read does not join
    # through it. The task cannot change startup, so this cannot go stale.
    startup_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("startup_profiles.id", ondelete="CASCADE"), index=True
    )

    # Display text only, echoed back to the founder. Never a path component --
    # see `core.storage.object_key`, which generates the key server-side.
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)

    # What R2 reported after the upload, not what the client claimed when it
    # asked for the URL. Null until the upload is confirmed.
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)

    status: Mapped[EvidenceStatus] = mapped_column(
        SAEnum(
            EvidenceStatus,
            native_enum=False,
            length=16,
            name="evidence_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=EvidenceStatus.PENDING,
        server_default=EvidenceStatus.PENDING.value,
        index=True,
    )

    outcome: Mapped[AssessmentOutcome | None] = mapped_column(
        SAEnum(
            AssessmentOutcome,
            native_enum=False,
            length=16,
            name="assessment_outcome",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        index=True,
    )
    """The grader's verdict, or NULL while the assessment is outstanding.

    NULL is "not graded yet", never "graded and inconclusive" -- inconclusive is
    `needs_more`, which is a real verdict with reasons attached.
    """

    # Founder-facing, and required on every outcome including a pass. Stored as
    # a JSON array rather than joined text so the client can render them as a
    # list without parsing.
    reasons: Mapped[list[str] | None] = mapped_column(JSONB)

    assessment_prompt_ref: Mapped[str | None] = mapped_column(String(60))
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Founder-safe failure reason when grading could not be completed at all.
    # Engineer-facing detail goes to the log, never to this column.
    error_code: Mapped[str | None] = mapped_column(String(60))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        return f"<Evidence {self.id} {self.status}/{self.outcome} task={self.task_id}>"
