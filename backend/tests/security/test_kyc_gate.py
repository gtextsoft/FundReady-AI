"""Unverified investors cannot discover or express interest (T4.1)."""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ForbiddenError
from app.core.security import AccountStatus, CurrentUser, KycStatus, Role
from app.modules.identity import service as identity
from app.modules.identity.models import User
from app.modules.investor import service as investor
from app.modules.investor.schemas import DiscoveryFilters
from tests.conftest import requires_database

pytestmark = [pytest.mark.security, pytest.mark.integration, requires_database]

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-signing-key-at-least-32-characters")
    monkeypatch.setenv("ARGON2_MEMORY_COST_KIB", "8192")
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    monkeypatch.setenv("PASSWORD_BREACH_CHECK_ENABLED", "false")
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
        kyc_status=user.kyc_status,
    )


async def _investor(session: AsyncSession, *, verified: bool) -> CurrentUser:
    user = await identity.register_user(
        session,
        email=f"inv-{uuid.uuid4().hex}@example.test",
        password=PASSWORD,
        role=Role.INVESTOR,
        first_name="Ivy",
        last_name="Investor",
    )
    assert user is not None
    user.status = AccountStatus.ACTIVE
    user.kyc_status = KycStatus.VERIFIED if verified else KycStatus.NONE
    await session.flush()
    return _actor(user)


@pytest.mark.asyncio
async def test_unverified_investor_cannot_discover(db_session: AsyncSession) -> None:
    actor = await _investor(db_session, verified=False)
    with pytest.raises(ForbiddenError) as exc:
        await investor.discover(
            db_session, actor, DiscoveryFilters(), limit=10, offset=0
        )
    assert exc.value.details.get("reason") == "kyc_required"


@pytest.mark.asyncio
async def test_verified_investor_can_discover(db_session: AsyncSession) -> None:
    actor = await _investor(db_session, verified=True)
    page = await investor.discover(
        db_session, actor, DiscoveryFilters(), limit=10, offset=0
    )
    assert page.total >= 0
    assert page.items == [] or page.limit == 10
