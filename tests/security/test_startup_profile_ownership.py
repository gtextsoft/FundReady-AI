"""Startup profile ownership.

The first founder-owned data in the system, so the first place tenant isolation
has to hold (`DECISIONS.md` D13, `AUTH.md` §6). A founder's business plan and
financials are competitively sensitive: one bug here is not a bug, it is a
breach.

Asserted here:

* a founder reaches only their own profile, by any route
* another founder's id returns **404, not 403**, so the API does not confirm
  which ids exist
* `owner_id` comes from the token and cannot be set from the request body
* a SACI admin can read anything (`AUTH.md` §2)
* unknown field names are refused rather than stored
"""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.core.security import AccountStatus, CurrentUser, Role
from app.modules.identity import service as identity
from app.modules.identity.models import User
from app.modules.intake import service
from app.modules.intake.fields import REQUIRED_COLUMNS, Stage
from app.modules.intake.repository import StartupProfileRepository
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


def unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.test"


def actor_for(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        role=user.role,
        status=AccountStatus.ACTIVE,
        email_verified=True,
        mfa_enabled=user.mfa_enabled,
    )


async def make_founder(
    session: AsyncSession, role: Role = Role.FOUNDER
) -> tuple[User, CurrentUser]:
    user = await identity.register_user(
        session, email=unique_email(), password=PASSWORD, role=Role.FOUNDER
    )
    assert user is not None
    user.role = role
    user.status = AccountStatus.ACTIVE
    await session.flush()
    return user, actor_for(user)


PROFILE = {
    "name": "Kanmi Logistics",
    "sector": "last-mile delivery",
    "stage": Stage.SEED.value,
    "country": "NG",
    "currency": "NGN",
}


class TestIsolation:
    async def test_a_founder_reads_their_own_profile(
        self, db_session: AsyncSession
    ) -> None:
        _, actor = await make_founder(db_session)
        created = await service.create_profile(db_session, actor, dict(PROFILE))

        found = await service.get_profile(db_session, actor, created.id)

        assert found.id == created.id

    async def test_another_founder_gets_404_not_403(
        self, db_session: AsyncSession
    ) -> None:
        """403 would confirm the id exists. 404 tells them nothing."""
        _, owner = await make_founder(db_session)
        victim_profile = await service.create_profile(db_session, owner, dict(PROFILE))
        _, attacker = await make_founder(db_session)

        with pytest.raises(NotFoundError):
            await service.get_profile(db_session, attacker, victim_profile.id)

    async def test_the_two_denials_are_indistinguishable(
        self, db_session: AsyncSession
    ) -> None:
        """Someone else's profile must read exactly like one that never existed."""
        _, owner = await make_founder(db_session)
        real = await service.create_profile(db_session, owner, dict(PROFILE))
        _, attacker = await make_founder(db_session)

        with pytest.raises(NotFoundError) as existing:
            await service.get_profile(db_session, attacker, real.id)
        with pytest.raises(NotFoundError) as imaginary:
            await service.get_profile(db_session, attacker, uuid.uuid4())

        assert existing.value.message == imaginary.value.message

    async def test_another_founder_cannot_update(
        self, db_session: AsyncSession
    ) -> None:
        _, owner = await make_founder(db_session)
        profile = await service.create_profile(db_session, owner, dict(PROFILE))
        _, attacker = await make_founder(db_session)

        with pytest.raises(NotFoundError):
            await service.update_profile(
                db_session, attacker, profile.id, {"name": "Stolen"}
            )

        assert profile.name == "Kanmi Logistics", "the row must be untouched"

    async def test_own_profile_lookup_never_returns_anothers(
        self, db_session: AsyncSession
    ) -> None:
        """The /me route resolves by owner, so it cannot be pointed elsewhere."""
        _, owner = await make_founder(db_session)
        await service.create_profile(db_session, owner, dict(PROFILE))
        _, other = await make_founder(db_session)

        with pytest.raises(NotFoundError):
            await service.get_own_profile(db_session, other)

    async def test_an_investor_cannot_read_a_profile(
        self, db_session: AsyncSession
    ) -> None:
        """Investors get summaries in T4.2, never the founder-facing record."""
        _, owner = await make_founder(db_session)
        profile = await service.create_profile(db_session, owner, dict(PROFILE))
        _, investor = await make_founder(db_session, role=Role.INVESTOR)

        with pytest.raises(NotFoundError):
            await service.get_profile(db_session, investor, profile.id)

    async def test_an_admin_can_read_any_profile(
        self, db_session: AsyncSession
    ) -> None:
        """SACI sees everything (AUTH.md section 2)."""
        _, owner = await make_founder(db_session)
        profile = await service.create_profile(db_session, owner, dict(PROFILE))
        _, admin = await make_founder(db_session, role=Role.ADMIN)

        found = await service.get_profile(db_session, admin, profile.id)

        assert found.id == profile.id


class TestOwnershipCannotBeSupplied:
    async def test_owner_comes_from_the_token(self, db_session: AsyncSession) -> None:
        """A client-supplied owner is how one founder's data lands under another."""
        _, victim = await make_founder(db_session)
        _, attacker = await make_founder(db_session)

        created = await service.create_profile(db_session, attacker, dict(PROFILE))

        assert created.owner_id == attacker.id
        assert created.owner_id != victim.id

    async def test_owner_id_is_not_an_accepted_field(self) -> None:
        """The schema rejects it outright, so it never reaches the service."""
        from pydantic import ValidationError

        from app.modules.intake.schemas import StartupProfileCreate

        with pytest.raises(ValidationError):
            StartupProfileCreate(owner_id=str(uuid.uuid4()))  # type: ignore[call-arg]

    async def test_one_profile_per_founder(self, db_session: AsyncSession) -> None:
        _, actor = await make_founder(db_session)
        await service.create_profile(db_session, actor, dict(PROFILE))

        with pytest.raises(ConflictError):
            await service.create_profile(db_session, actor, dict(PROFILE))


class TestFieldHandling:
    async def test_unknown_field_names_are_refused(self) -> None:
        """A typo must not become a field no audit will ever read."""
        from pydantic import ValidationError

        from app.modules.intake.schemas import StartupProfileUpdate

        with pytest.raises(ValidationError, match="unknown profile fields"):
            StartupProfileUpdate(
                fields={"revenue_last_month": {"value": 1, "source": "founder"}}
            )

    async def test_fields_merge_rather_than_replace(
        self, db_session: AsyncSession
    ) -> None:
        """Extraction must not wipe what the founder typed."""
        _, actor = await make_founder(db_session)
        profile = await service.create_profile(
            db_session,
            actor,
            {
                **PROFILE,
                "fields": {
                    "description": {"value": "Typed by hand", "source": "founder"}
                },
            },
        )

        await service.update_profile(
            db_session,
            actor,
            profile.id,
            {
                "fields": {
                    "monthly_revenue_minor": {
                        "value": 4500000,
                        "source": "document",
                        "confidence": 0.82,
                    }
                }
            },
        )

        assert profile.fields["description"]["value"] == "Typed by hand"
        assert profile.fields["monthly_revenue_minor"]["value"] == 4500000

    async def test_provenance_is_stored_with_the_value(
        self, db_session: AsyncSession
    ) -> None:
        """The audit has to cite its evidence (CLAUDE.md section 5)."""
        _, actor = await make_founder(db_session)
        profile = await service.create_profile(
            db_session,
            actor,
            {
                **PROFILE,
                "fields": {
                    "monthly_revenue_minor": {
                        "value": 4500000,
                        "source": "document",
                        "confidence": 0.82,
                    }
                },
            },
        )

        stored = profile.fields["monthly_revenue_minor"]
        assert stored["source"] == "document"
        assert stored["confidence"] == 0.82

    async def test_a_partial_profile_is_allowed(self, db_session: AsyncSession) -> None:
        """A founder can start with a name and come back later."""
        _, actor = await make_founder(db_session)

        profile = await service.create_profile(db_session, actor, {"name": "Just this"})

        assert profile.name == "Just this"
        assert profile.sector is None

    async def test_missing_fields_reports_the_gap(
        self, db_session: AsyncSession
    ) -> None:
        _, actor = await make_founder(db_session)
        profile = await service.create_profile(db_session, actor, {"name": "Sparse"})

        gaps = service.missing_fields(profile)

        for column in REQUIRED_COLUMNS:
            if column != "name":
                assert column in gaps
        assert "monthly_revenue_minor" in gaps

    async def test_missing_fields_shrinks_as_it_is_filled(
        self, db_session: AsyncSession
    ) -> None:
        _, actor = await make_founder(db_session)
        profile = await service.create_profile(db_session, actor, dict(PROFILE))
        before = service.missing_fields(profile)

        await service.update_profile(
            db_session,
            actor,
            profile.id,
            {"fields": {"team_size": {"value": 7, "source": "founder"}}},
        )

        after = service.missing_fields(profile)
        assert "team_size" in before
        assert "team_size" not in after

    async def test_an_empty_value_still_counts_as_missing(
        self, db_session: AsyncSession
    ) -> None:
        """`{"value": null}` is a placeholder, not an answer."""
        _, actor = await make_founder(db_session)
        profile = await service.create_profile(
            db_session,
            actor,
            {**PROFILE, "fields": {"team_size": {"value": None, "source": "founder"}}},
        )

        assert "team_size" in service.missing_fields(profile)


class TestServerGeneratedColumns:
    async def test_timestamps_are_readable_after_an_update(
        self, db_session: AsyncSession
    ) -> None:
        """Regression: reading `updated_at` after a flush raised MissingGreenlet.

        With `onupdate=func.now()` the new value is computed server-side, so the
        ORM expires the attribute and reading it back triggers lazy IO -- which
        async SQLAlchemy cannot do outside its greenlet. Every response includes
        `updated_at`, so PATCH returned 500 while every service-level test
        passed, because none of them read the column.
        """
        _, actor = await make_founder(db_session)
        profile = await service.create_profile(db_session, actor, dict(PROFILE))

        await service.update_profile(db_session, actor, profile.id, {"name": "Renamed"})

        # Both must be readable without further IO.
        assert profile.created_at is not None
        assert profile.updated_at is not None
        assert profile.name == "Renamed"

    async def test_a_profile_serialises_after_an_update(
        self, db_session: AsyncSession
    ) -> None:
        """What the router actually does, which is where the 500 surfaced."""
        from app.modules.intake.router import _serialise

        _, actor = await make_founder(db_session)
        profile = await service.create_profile(db_session, actor, dict(PROFILE))
        updated = await service.update_profile(
            db_session, actor, profile.id, {"name": "Renamed"}
        )

        assert _serialise(updated).name == "Renamed"


class TestSectorIsOpenEnded:
    async def test_a_sector_that_does_not_exist_yet_is_accepted(
        self, db_session: AsyncSession
    ) -> None:
        """DECISIONS.md D11: any sector, including ones invented tomorrow."""
        _, actor = await make_founder(db_session)

        profile = await service.create_profile(
            db_session,
            actor,
            {**PROFILE, "sector": "orbital debris insurance brokerage"},
        )

        assert profile.sector == "orbital debris insurance brokerage"


class TestRepositoryDoesNotHideTheCheck:
    async def test_the_repository_returns_any_profile(
        self, db_session: AsyncSession
    ) -> None:
        """Deliberate: ownership is the service's job, in one auditable place.

        If the repository scoped its own queries, the service's checks would look
        redundant and the first unscoped query added later would be the hole.
        This test documents that the wall is where we think it is.
        """
        _, owner = await make_founder(db_session)
        profile = await service.create_profile(db_session, owner, dict(PROFILE))

        unscoped = await StartupProfileRepository(db_session).get(profile.id)

        assert unscoped is not None
        assert unscoped.owner_id == owner.id


class TestCascade:
    async def test_deleting_a_user_removes_their_profile(
        self, db_session: AsyncSession
    ) -> None:
        """A founder's data should not outlive their account."""
        user, actor = await make_founder(db_session)
        await service.create_profile(db_session, actor, dict(PROFILE))

        await db_session.execute(
            text("delete from users where id = :id"), {"id": user.id}
        )
        await db_session.flush()

        remaining = (
            await db_session.execute(
                text("select count(*) from startup_profiles where owner_id = :id"),
                {"id": user.id},
            )
        ).scalar_one()
        assert remaining == 0
