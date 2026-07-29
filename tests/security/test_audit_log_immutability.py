"""The audit log is append-only, enforced by the database.

`AUTH.md` section 9 requires every admin action -- above all a full-report
reveal (DECISIONS.md D8) -- to be recorded immutably. A log the application
merely promises not to modify is not evidence of anything, so these tests go
around the application entirely and issue raw SQL. If a future migration, ORM
change, or careless query could rewrite history, it fails here.

Every test runs inside a transaction that is rolled back, so nothing is left
behind -- which is also the only way to test a table that refuses DELETE.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import AuditAction
from app.modules.identity.service import record_action
from tests.conftest import requires_database

pytestmark = [pytest.mark.security, pytest.mark.integration, requires_database]


async def _seed(session: AsyncSession) -> uuid.UUID:
    entry = await record_action(
        session,
        AuditAction.REPORT_REVEALED,
        actor_id=uuid.uuid4(),
        target_type="startup",
        target_id=uuid.uuid4(),
        details={"reason": "meeting"},
    )
    await session.flush()
    return entry.id


async def test_an_entry_can_be_written(db_session: AsyncSession) -> None:
    entry_id = await _seed(db_session)

    stored = (
        await db_session.execute(
            text("select action from audit_log where id = :id"), {"id": entry_id}
        )
    ).scalar_one()

    assert stored == AuditAction.REPORT_REVEALED.value


@pytest.mark.parametrize(
    ("operation", "statement"),
    [
        ("UPDATE", "update audit_log set action = 'tampered' where id = :id"),
        ("DELETE", "delete from audit_log where id = :id"),
        ("TRUNCATE", "truncate audit_log"),
    ],
)
async def test_mutation_is_rejected_by_the_database(
    db_session: AsyncSession, operation: str, statement: str
) -> None:
    """Raw SQL, not the ORM: the guarantee has to hold below the application."""
    entry_id = await _seed(db_session)

    savepoint = await db_session.begin_nested()
    with pytest.raises(DBAPIError) as exc_info:
        await db_session.execute(text(statement), {"id": entry_id})
    await savepoint.rollback()

    assert "append-only" in str(exc_info.value)
    assert operation in str(exc_info.value)


async def test_the_entry_survives_the_attempts(db_session: AsyncSession) -> None:
    """After a rejected UPDATE the original row must still be intact."""
    entry_id = await _seed(db_session)

    savepoint = await db_session.begin_nested()
    with pytest.raises(DBAPIError):
        await db_session.execute(
            text("update audit_log set action = 'tampered' where id = :id"),
            {"id": entry_id},
        )
    await savepoint.rollback()

    action = (
        await db_session.execute(
            text("select action from audit_log where id = :id"), {"id": entry_id}
        )
    ).scalar_one()

    assert action == AuditAction.REPORT_REVEALED.value


async def test_the_guards_are_actually_installed(db_session: AsyncSession) -> None:
    """A dropped trigger would silently remove the guarantee."""
    triggers = (
        (
            await db_session.execute(
                text(
                    "select tgname from pg_trigger t "
                    "join pg_class c on c.oid = t.tgrelid "
                    "where c.relname = 'audit_log' and not t.tgisinternal"
                )
            )
        )
        .scalars()
        .all()
    )

    assert "audit_log_no_update_or_delete" in triggers
    # TRUNCATE does not fire row-level triggers, so it needs its own.
    assert "audit_log_no_truncate" in triggers
