"""Readiness data access.

Layer: **repository** (ARCHITECTURE.md section 3) -- database access only.
Queries in, models/data out. No business rules, no authorization decisions.

Nothing here filters by owner, for the reason the intake and audit repositories
state: ownership is an authorization decision and lives in the service (D13).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.readiness.evidence import EvidenceStatus
from app.modules.readiness.generation import Requirement, TaskStatus
from app.modules.readiness.models import Evidence, ReadinessTask


class ReadinessTaskRepository:
    """Read and write readiness tasks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, task_id: uuid.UUID) -> ReadinessTask | None:
        return await self._session.get(ReadinessTask, task_id)

    async def list_for_startup(
        self,
        startup_id: uuid.UUID,
        *,
        status: TaskStatus | None = None,
        requirement: Requirement | None = None,
        audit_run_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ReadinessTask], int]:
        """One page of this startup's tasks, plus the unpaginated total.

        **Priority first, then required, then worst-scoring dimension.** A
        founder opening the list sees the few things the report singled out,
        then everything that blocks the gate, then the rest -- the same
        worst-first intent `synthesis._action_plan` encodes, expressed as an
        ORDER BY so paging is stable. `created_at` and `id` break every
        remaining tie, because a LIMIT/OFFSET over a non-deterministic order can
        show the same row on two pages and drop another entirely.

        Unscoreable dimensions carry a NULL score and sort **first**: "we could
        not assess this" is more urgent than "this scored 40", per the same
        reasoning in the action plan. Postgres sorts NULLs last on ASC by
        default, so it is asked for explicitly.

        The count is a second statement rather than a window function: it has to
        ignore LIMIT/OFFSET, and `CLAUDE.md` section 6 wants `total` on every
        list so a client can render "page N of M".
        """
        query: Select[tuple[ReadinessTask]] = select(ReadinessTask).where(
            ReadinessTask.startup_id == startup_id
        )
        if status is not None:
            query = query.where(ReadinessTask.status == status)
        if requirement is not None:
            query = query.where(ReadinessTask.requirement == requirement)
        if audit_run_id is not None:
            # "Raised by this report", which is what the readiness gate counts.
            # `audit_run_id` is refreshed to the newest run on every
            # regeneration, so this selects the current plan rather than every
            # task the startup has ever been given.
            query = query.where(ReadinessTask.audit_run_id == audit_run_id)

        total = await self._session.scalar(
            select(func.count()).select_from(query.subquery())
        )

        # 'recommended' sorts before 'required' alphabetically, which is the
        # wrong way round, so the required rows are lifted by an explicit
        # boolean rather than by the column's own collation.
        ordered = query.order_by(
            ReadinessTask.is_priority.desc(),
            (ReadinessTask.requirement == Requirement.REQUIRED).desc(),
            ReadinessTask.dimension_score.asc().nulls_first(),
            ReadinessTask.created_at.asc(),
            ReadinessTask.id.asc(),
        )
        rows = await self._session.scalars(ordered.limit(limit).offset(offset))
        return list(rows), int(total or 0)

    async def find_by_fingerprints(
        self, startup_id: uuid.UUID, fingerprints: Sequence[str]
    ) -> dict[str, ReadinessTask]:
        """The stored tasks matching any of these gaps, keyed by fingerprint.

        One statement for the whole plan rather than a lookup per action: a
        report can raise 44 of them, and 44 round trips inside a worker's
        transaction is latency a founder waits through.
        """
        if not fingerprints:
            return {}
        rows = await self._session.scalars(
            select(ReadinessTask).where(
                ReadinessTask.startup_id == startup_id,
                ReadinessTask.action_fingerprint.in_(fingerprints),
            )
        )
        return {row.action_fingerprint: row for row in rows}

    async def list_by_status(
        self, startup_id: uuid.UUID, statuses: Sequence[TaskStatus]
    ) -> list[ReadinessTask]:
        """Every task of this startup currently in one of `statuses`."""
        if not statuses:
            return []
        rows = await self._session.scalars(
            select(ReadinessTask).where(
                ReadinessTask.startup_id == startup_id,
                ReadinessTask.status.in_(statuses),
            )
        )
        return list(rows)

    async def add(self, task: ReadinessTask) -> ReadinessTask:
        self._session.add(task)
        await self._session.flush()
        return task


class EvidenceRepository:
    """Read and write evidence uploads.

    Ownership is the service's decision here too (D13); nothing below filters
    by owner.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, evidence_id: uuid.UUID) -> Evidence | None:
        return await self._session.get(Evidence, evidence_id)

    async def list_for_task(
        self, task_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[Evidence], int]:
        """This task's submissions, newest first, plus the unpaginated total.

        Newest first because the founder's question is "how did my last
        submission do"; the older ones are history. `id` breaks ties so paging
        is stable when two rows share a timestamp.
        """
        query: Select[tuple[Evidence]] = select(Evidence).where(
            Evidence.task_id == task_id
        )
        total = await self._session.scalar(
            select(func.count()).select_from(query.subquery())
        )
        rows = await self._session.scalars(
            query.order_by(Evidence.created_at.desc(), Evidence.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    async def list_gradable(self, task_id: uuid.UUID) -> list[Evidence]:
        """Every `ready`, not-yet-graded submission for this task, oldest first.

        The grader reads a task's whole outstanding submission set rather than
        one file: a founder proving "publish a pricing page" may reasonably
        attach a screenshot *and* the invoice that dates it, and grading those
        separately would fail both for being incomplete on their own.
        """
        rows = await self._session.scalars(
            select(Evidence)
            .where(
                Evidence.task_id == task_id,
                Evidence.status == EvidenceStatus.READY,
                Evidence.outcome.is_(None),
            )
            .order_by(Evidence.created_at.asc(), Evidence.id.asc())
        )
        return list(rows)

    async def list_passed_for_startup(self, startup_id: uuid.UUID) -> list[Evidence]:
        """Every stored submission behind a task that is currently passed.

        Joined to the task rather than filtered on `Evidence.outcome`, and the
        difference matters: a task that was reopened and graded again should not
        keep feeding the audit evidence from the grading that was overturned.
        The task's **current** status is the question, so the task is what is
        asked.

        Ordered by creation so the audit's document list -- and therefore its
        idempotency fingerprint -- is stable across calls.
        """
        rows = await self._session.scalars(
            select(Evidence)
            .join(ReadinessTask, ReadinessTask.id == Evidence.task_id)
            .where(
                Evidence.startup_id == startup_id,
                Evidence.status == EvidenceStatus.READY,
                ReadinessTask.status == TaskStatus.PASSED,
            )
            .order_by(Evidence.created_at.asc(), Evidence.id.asc())
        )
        return list(rows)

    async def add(self, evidence: Evidence) -> Evidence:
        self._session.add(evidence)
        await self._session.flush()
        return evidence
