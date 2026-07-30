"""Admin user management.

The admin role can reveal any full report (`DECISIONS.md` D8), so the questions
worth asking are: who can create one, can an admin lock everyone out, does a
suspension take effect immediately, and is every action attributable.

`AUTH.md` §9 requires the audit log. The `session_valid_after` bump is asserted
only where it means something -- suspension and role change -- and deliberately
not on provisioning (no session exists) or reactivation (the suspension already
moved it).
"""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthenticatedError,
)
from app.core.security import AccountStatus, CurrentUser, Role
from app.modules.identity import service
from app.modules.identity.models import AuditAction, AuditLog, User
from app.modules.identity.repository import UserRepository
from tests.conftest import requires_database

pytestmark = [pytest.mark.security, pytest.mark.integration, requires_database]

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-signing-key-at-least-32-characters")
    monkeypatch.setenv("MFA_SECRET_ENCRYPTION_KEY", "a-dev-mfa-key-32-characters-long!")
    monkeypatch.setenv("ARGON2_MEMORY_COST_KIB", "8192")
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.test"


def actor_for(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        role=user.role,
        status=user.status,
        email_verified=user.email_verified,
        mfa_enabled=user.mfa_enabled,
    )


async def make_user(
    session: AsyncSession,
    role: Role = Role.FOUNDER,
    status: AccountStatus = AccountStatus.ACTIVE,
) -> User:
    user = await service.register_user(
        session,
        email=unique_email(),
        password=PASSWORD,
        role=Role.FOUNDER,
        first_name="Ada",
        last_name="Tester",
    )
    assert user is not None
    user.role = role
    user.status = status
    await session.flush()
    return user


async def make_admin(session: AsyncSession) -> tuple[User, CurrentUser]:
    admin = await make_user(session, role=Role.ADMIN)
    admin.mfa_enabled = True
    await session.flush()
    return admin, actor_for(admin)


@pytest.fixture(autouse=True)
async def no_pre_existing_admins(db_session: AsyncSession) -> None:
    """Fail loudly if the database already has an active admin.

    `count_active_admins()` is a global count by nature -- the invariant it
    guards ("never zero administrators") cannot be scoped to a transaction. So
    the last-admin tests below assume they are the only admins present. If a
    real admin gets created in this database, they would fail in a way that
    looks like a bug in the guard rather than a dirty fixture. This turns that
    into a clear message.
    """
    existing = await UserRepository(db_session).count_active_admins()
    assert existing == 0, (
        f"{existing} active admin(s) already in the test database; the "
        "last-admin tests need a database with none"
    )


async def actions_for(session: AsyncSession, target: uuid.UUID) -> list[str]:
    return list(
        await session.scalars(
            select(AuditLog.action).where(AuditLog.target_id == str(target))
        )
    )


class TestProvisioning:
    async def test_an_admin_can_create_an_admin(self, db_session: AsyncSession) -> None:
        _, actor = await make_admin(db_session)

        created = await service.provision_admin(
            db_session, actor, email=unique_email(), password=PASSWORD
        )

        assert created.role is Role.ADMIN

    async def test_the_new_admin_has_no_power_yet(
        self, db_session: AsyncSession
    ) -> None:
        """Unverified and without MFA, so `require_role(ADMIN)` refuses them."""
        _, actor = await make_admin(db_session)

        created = await service.provision_admin(
            db_session, actor, email=unique_email(), password=PASSWORD
        )

        assert created.status is AccountStatus.PENDING_VERIFICATION
        assert created.mfa_enabled is False

    @pytest.mark.parametrize("role", [Role.FOUNDER, Role.INVESTOR])
    async def test_a_non_admin_cannot_provision(
        self, db_session: AsyncSession, role: Role
    ) -> None:
        """Service-layer check, independent of the route dependency."""
        user = await make_user(db_session, role=role)

        with pytest.raises(ForbiddenError):
            await service.provision_admin(
                db_session, actor_for(user), email=unique_email(), password=PASSWORD
            )

    async def test_self_registration_still_cannot_reach_admin(
        self, db_session: AsyncSession
    ) -> None:
        with pytest.raises(ForbiddenError):
            await service.register_user(
                db_session,
                email=unique_email(),
                password=PASSWORD,
                role=Role.ADMIN,
                first_name="Ada",
                last_name="Tester",
            )

    async def test_a_duplicate_address_is_a_real_error(
        self, db_session: AsyncSession
    ) -> None:
        """Unlike registration: the caller is trusted, so silence would be worse."""
        _, actor = await make_admin(db_session)
        existing = await make_user(db_session)

        with pytest.raises(ConflictError):
            await service.provision_admin(
                db_session, actor, email=existing.email, password=PASSWORD
            )

    async def test_provisioning_is_attributable(self, db_session: AsyncSession) -> None:
        admin, actor = await make_admin(db_session)

        created = await service.provision_admin(
            db_session, actor, email=unique_email(), password=PASSWORD
        )

        entry = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.target_id == str(created.id),
                AuditLog.action == AuditAction.ADMIN_PROVISIONED.value,
            )
        )
        assert entry is not None
        assert entry.actor_id == admin.id, "who did it must be recorded"

    async def test_a_weak_password_is_rejected(self, db_session: AsyncSession) -> None:
        _, actor = await make_admin(db_session)

        with pytest.raises(Exception, match="12 characters"):
            await service.provision_admin(
                db_session, actor, email=unique_email(), password="short"
            )


class TestSuspension:
    async def test_suspension_ends_sessions_immediately(
        self, db_session: AsyncSession
    ) -> None:
        """A suspension exists to evict, not to take effect at token expiry."""
        _, actor = await make_admin(db_session)
        target = await make_user(db_session)
        pair = await service.issue_tokens(db_session, target)

        suspended = await service.suspend_user(db_session, actor, target.id)

        assert suspended.status is AccountStatus.SUSPENDED
        assert suspended.session_valid_after is not None
        with pytest.raises((UnauthenticatedError, ForbiddenError)):
            await service.refresh_tokens(db_session, pair.refresh_token)

    async def test_a_suspended_user_cannot_log_in(
        self, db_session: AsyncSession
    ) -> None:
        _, actor = await make_admin(db_session)
        target = await make_user(db_session)

        await service.suspend_user(db_session, actor, target.id)

        with pytest.raises(ForbiddenError):
            await service.authenticate(
                db_session, email=target.email, password=PASSWORD
            )

    async def test_an_admin_cannot_suspend_themselves(
        self, db_session: AsyncSession
    ) -> None:
        admin, actor = await make_admin(db_session)

        with pytest.raises(ForbiddenError):
            await service.suspend_user(db_session, actor, admin.id)

    async def test_suspending_the_only_other_admin_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        _, actor = await make_admin(db_session)
        lone = await make_user(db_session, role=Role.ADMIN)
        # Remove the actor from the active-admin count so `lone` is the last.
        actor_record = await UserRepository(db_session).get_by_id(actor.id)
        assert actor_record is not None
        actor_record.status = AccountStatus.PENDING_VERIFICATION
        await db_session.flush()

        with pytest.raises(ConflictError):
            await service.suspend_user(db_session, actor, lone.id)

    async def test_an_unknown_user_is_not_found(self, db_session: AsyncSession) -> None:
        _, actor = await make_admin(db_session)

        with pytest.raises(NotFoundError):
            await service.suspend_user(db_session, actor, uuid.uuid4())

    async def test_suspension_is_audit_logged(self, db_session: AsyncSession) -> None:
        _, actor = await make_admin(db_session)
        target = await make_user(db_session)

        await service.suspend_user(db_session, actor, target.id)

        assert AuditAction.USER_SUSPENDED.value in await actions_for(
            db_session, target.id
        )


class TestReactivation:
    async def test_a_verified_user_returns_to_active(
        self, db_session: AsyncSession
    ) -> None:
        _, actor = await make_admin(db_session)
        target = await make_user(db_session)
        target.email_verified_at = target.created_at
        await db_session.flush()
        await service.suspend_user(db_session, actor, target.id)

        reactivated = await service.reactivate_user(db_session, actor, target.id)

        assert reactivated.status is AccountStatus.ACTIVE

    async def test_an_unverified_user_returns_to_pending(
        self, db_session: AsyncSession
    ) -> None:
        """Reactivating must not confer email verification."""
        _, actor = await make_admin(db_session)
        target = await make_user(db_session, status=AccountStatus.PENDING_VERIFICATION)
        await service.suspend_user(db_session, actor, target.id)

        reactivated = await service.reactivate_user(db_session, actor, target.id)

        assert reactivated.status is AccountStatus.PENDING_VERIFICATION

    async def test_reactivating_an_active_account_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        _, actor = await make_admin(db_session)
        target = await make_user(db_session)

        with pytest.raises(ConflictError):
            await service.reactivate_user(db_session, actor, target.id)

    async def test_reactivation_is_audit_logged(self, db_session: AsyncSession) -> None:
        _, actor = await make_admin(db_session)
        target = await make_user(db_session)
        await service.suspend_user(db_session, actor, target.id)

        await service.reactivate_user(db_session, actor, target.id)

        assert AuditAction.USER_REACTIVATED.value in await actions_for(
            db_session, target.id
        )


class TestRoleChange:
    async def test_a_role_can_be_changed(self, db_session: AsyncSession) -> None:
        _, actor = await make_admin(db_session)
        target = await make_user(db_session, role=Role.FOUNDER)

        changed = await service.change_user_role(
            db_session, actor, target.id, Role.INVESTOR
        )

        assert changed.role is Role.INVESTOR

    async def test_a_role_change_forces_re_authentication(
        self, db_session: AsyncSession
    ) -> None:
        """The new role has to apply now, not whenever the token expires."""
        _, actor = await make_admin(db_session)
        target = await make_user(db_session)
        pair = await service.issue_tokens(db_session, target)

        await service.change_user_role(db_session, actor, target.id, Role.INVESTOR)

        assert target.session_valid_after is not None
        with pytest.raises(UnauthenticatedError):
            await service.refresh_tokens(db_session, pair.refresh_token)

    async def test_an_admin_cannot_change_their_own_role(
        self, db_session: AsyncSession
    ) -> None:
        admin, actor = await make_admin(db_session)

        with pytest.raises(ForbiddenError):
            await service.change_user_role(db_session, actor, admin.id, Role.FOUNDER)

    async def test_demoting_the_last_admin_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        _, actor = await make_admin(db_session)
        lone = await make_user(db_session, role=Role.ADMIN)
        actor_record = await UserRepository(db_session).get_by_id(actor.id)
        assert actor_record is not None
        actor_record.status = AccountStatus.PENDING_VERIFICATION
        await db_session.flush()

        with pytest.raises(ConflictError):
            await service.change_user_role(db_session, actor, lone.id, Role.FOUNDER)

    async def test_promoting_to_admin_is_allowed(
        self, db_session: AsyncSession
    ) -> None:
        _, actor = await make_admin(db_session)
        target = await make_user(db_session, role=Role.FOUNDER)

        changed = await service.change_user_role(
            db_session, actor, target.id, Role.ADMIN
        )

        assert changed.role is Role.ADMIN
        assert changed.mfa_enabled is False, "promotion confers no second factor"

    async def test_a_no_op_change_is_refused(self, db_session: AsyncSession) -> None:
        _, actor = await make_admin(db_session)
        target = await make_user(db_session, role=Role.FOUNDER)

        with pytest.raises(ConflictError):
            await service.change_user_role(db_session, actor, target.id, Role.FOUNDER)

    async def test_the_change_is_audit_logged_with_both_roles(
        self, db_session: AsyncSession
    ) -> None:
        _, actor = await make_admin(db_session)
        target = await make_user(db_session, role=Role.FOUNDER)

        await service.change_user_role(db_session, actor, target.id, Role.INVESTOR)

        entry = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.target_id == str(target.id),
                AuditLog.action == AuditAction.USER_ROLE_CHANGED.value,
            )
        )
        assert entry is not None
        assert entry.details["from"] == "founder"
        assert entry.details["to"] == "investor"


class TestAtomicity:
    async def test_a_refused_action_leaves_no_audit_row(
        self, db_session: AsyncSession
    ) -> None:
        """Otherwise the log would record attempts that never happened."""
        _, actor = await make_admin(db_session)
        target = await make_user(db_session, role=Role.FOUNDER)

        with pytest.raises(ConflictError):
            await service.change_user_role(db_session, actor, target.id, Role.FOUNDER)

        assert AuditAction.USER_ROLE_CHANGED.value not in await actions_for(
            db_session, target.id
        )

    async def test_a_successful_action_leaves_exactly_one(
        self, db_session: AsyncSession
    ) -> None:
        _, actor = await make_admin(db_session)
        target = await make_user(db_session)

        await service.suspend_user(db_session, actor, target.id)

        actions = await actions_for(db_session, target.id)
        assert actions.count(AuditAction.USER_SUSPENDED.value) == 1
