"""Admin stats, catalogue filters, and identity-stripped corpus export."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ForbiddenError
from app.core.security import AccountStatus, CurrentUser, Role
from app.modules.identity import service as identity
from app.modules.identity.models import AuditAction, User
from app.modules.identity.repository import AuditLogRepository
from app.modules.intake import service as intake
from app.modules.intake.fields import Stage
from tests.conftest import requires_database

pytestmark = [pytest.mark.security, pytest.mark.integration, requires_database]

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-signing-key-at-least-32-characters")
    monkeypatch.setenv("ARGON2_MEMORY_COST_KIB", "8192")
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _actor(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        role=user.role,
        status=AccountStatus.ACTIVE,
        email_verified=True,
        mfa_enabled=user.mfa_enabled,
    )


async def _user(session: AsyncSession, role: Role) -> tuple[User, CurrentUser]:
    user = await identity.register_user(
        session,
        email=f"user-{uuid.uuid4().hex}@example.test",
        password=PASSWORD,
        role=Role.FOUNDER,
        first_name="Ada",
        last_name="Tester",
    )
    assert user is not None
    user.role = role
    user.status = AccountStatus.ACTIVE
    if role is Role.ADMIN:
        user.mfa_enabled = True
    await session.flush()
    return user, _actor(user)


PROFILE = {
    "name": "Kanmi Logistics",
    "sector": "last-mile delivery",
    "stage": Stage.SEED.value,
    "country": "NG",
    "currency": "NGN",
    "fields": {
        "legal_name": {"value": "Kanmi Logistics Ltd", "source": "founder"},
        "registration_number": {"value": "RC-123456", "source": "founder"},
        "founder_email": {"value": "ada@kanmi.test", "source": "founder"},
        "website": {"value": "https://kanmi.test", "source": "founder"},
        "monthly_revenue_minor": {"value": 4500000, "source": "founder"},
    },
}


class TestAdminScale:
    async def test_founder_cannot_read_stats(self, db_session: AsyncSession) -> None:
        _, founder = await _user(db_session, Role.FOUNDER)
        with pytest.raises(ForbiddenError):
            await intake.admin_stats(db_session, founder)

    async def test_admin_stats_count_the_catalogue(
        self, db_session: AsyncSession
    ) -> None:
        _, founder = await _user(db_session, Role.FOUNDER)
        await intake.create_profile(db_session, founder, dict(PROFILE))
        _, admin = await _user(db_session, Role.ADMIN)

        stats = await intake.admin_stats(db_session, admin)

        assert stats.startups_total >= 1
        assert stats.users_founders >= 1
        assert stats.users_admins >= 1

    async def test_admin_can_search_startups(self, db_session: AsyncSession) -> None:
        _, founder = await _user(db_session, Role.FOUNDER)
        created = await intake.create_profile(db_session, founder, dict(PROFILE))
        _, admin = await _user(db_session, Role.ADMIN)

        rows, total = await intake.list_admin_startups(
            db_session,
            admin,
            verification=None,
            q="kanmi",
            country="NG",
            sector="last-mile delivery",
            stage=Stage.SEED,
            published=False,
            limit=20,
            offset=0,
        )

        assert total >= 1
        assert any(row.id == created.id for row in rows)

    async def test_founder_cannot_export_corpus(self, db_session: AsyncSession) -> None:
        _, founder = await _user(db_session, Role.FOUNDER)
        with pytest.raises(ForbiddenError):
            await intake.export_training_corpus(
                db_session, founder, limit=10, offset=0
            )

    async def test_corpus_strips_identity_and_is_logged(
        self, db_session: AsyncSession
    ) -> None:
        _, founder = await _user(db_session, Role.FOUNDER)
        created = await intake.create_profile(db_session, founder, dict(PROFILE))
        _, admin = await _user(db_session, Role.ADMIN)

        page = await intake.export_training_corpus(
            db_session,
            admin,
            startup_id=created.id,
            limit=10,
            offset=0,
        )

        assert page.purpose == "model_training"
        assert page.total == 1
        record = page.items[0]
        assert record.startup_id == created.id
        assert "legal_name" not in record.fields
        assert "registration_number" not in record.fields
        assert "founder_email" not in record.fields
        assert "website" not in record.fields
        assert "monthly_revenue_minor" in record.fields
        dumped = str(record.fields)
        assert "ada@kanmi.test" not in dumped
        assert "RC-123456" not in dumped

        logged = await AuditLogRepository(db_session).list_for_actor(actor_id=admin.id)
        assert any(row.action == AuditAction.CORPUS_EXPORTED.value for row in logged)
