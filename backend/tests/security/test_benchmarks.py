"""The benchmark knowledge base (T2.3).

A benchmark is the yardstick every verdict is measured against, so a wrong or
attacker-supplied row is a wrong verdict for **every** startup scored against
it -- not one tenant's problem but all of them. Two things are asserted here:

* **only SACI admins write, and only admins read.** Founders and investors get
  `403`. Publishing the set would tell a founder exactly what to claim, and
  letting one edit it would let them move their own goalposts.
* **the fallback chain resolves in a stated order and says which rung matched.**
  Sector is free text (D11), so an exact match misses more often than it hits;
  the chain is the feature. Returning a number without its match quality would
  let the rubric score confidently off an all-sectors global median.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, InvalidRequestError
from app.core.security import AccountStatus, CurrentUser, Role
from app.modules.audit import service
from app.modules.audit.benchmarks import (
    ANY_SECTOR,
    GLOBAL_REGION,
    BenchmarkMetric,
    MatchQuality,
    Stage,
)
from app.modules.identity import service as identity
from app.modules.identity.models import AuditAction
from app.modules.identity.repository import AuditLogRepository
from tests.conftest import requires_database

pytestmark = [pytest.mark.security, pytest.mark.integration, requires_database]

PASSWORD = "correct-horse-battery-staple"
MARGIN = BenchmarkMetric.GROSS_MARGIN_PERCENT


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-signing-key-at-least-32-characters")
    monkeypatch.setenv("ARGON2_MEMORY_COST_KIB", "8192")
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def actor_with_role(session: AsyncSession, role: Role) -> CurrentUser:
    user = await identity.register_user(
        session,
        email=f"user-{uuid.uuid4().hex}@kanmi-logistics.com",
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
    user.email_verified_at = datetime.now(UTC)
    await session.flush()
    return CurrentUser(
        id=user.id,
        role=role,
        status=AccountStatus.ACTIVE,
        email_verified=True,
        mfa_enabled=(role is Role.ADMIN),
    )


def band(
    sector: str = "logistics",
    region: str = "NG",
    stage: Stage = Stage.SEED,
    metric: BenchmarkMetric = MARGIN,
    **overrides: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "sector": sector,
        "stage": stage,
        "metric": metric,
        "region": region,
        "p25": Decimal("18"),
        "p50": Decimal("27.5"),
        "p75": Decimal("36"),
        "source": "SACI portfolio review, Q2 2026",
        "as_of_date": date(2026, 6, 30),
    }
    payload.update(overrides)
    return payload


class TestOnlyAdminsTouchBenchmarks:
    @pytest.mark.parametrize("role", [Role.FOUNDER, Role.INVESTOR])
    async def test_a_non_admin_cannot_create(
        self, db_session: AsyncSession, role: Role
    ) -> None:
        """A founder who could write benchmarks could move their own goalposts."""
        actor = await actor_with_role(db_session, role)

        with pytest.raises(ForbiddenError):
            await service.create_benchmark(db_session, actor, band())

    @pytest.mark.parametrize("role", [Role.FOUNDER, Role.INVESTOR])
    async def test_a_non_admin_cannot_read(
        self, db_session: AsyncSession, role: Role
    ) -> None:
        """Publishing the set tells a founder exactly what to claim."""
        actor = await actor_with_role(db_session, role)

        with pytest.raises(ForbiddenError):
            await service.list_benchmarks(db_session, actor)

    async def test_a_non_admin_cannot_retire(self, db_session: AsyncSession) -> None:
        admin = await actor_with_role(db_session, Role.ADMIN)
        created = await service.create_benchmark(db_session, admin, band())
        founder = await actor_with_role(db_session, Role.FOUNDER)

        with pytest.raises(ForbiddenError):
            await service.retire_benchmark(db_session, founder, created.id)

    async def test_an_admin_can(self, db_session: AsyncSession) -> None:
        admin = await actor_with_role(db_session, Role.ADMIN)

        created = await service.create_benchmark(db_session, admin, band())

        assert created.metric is MARGIN


class TestEveryWriteIsLogged:
    """`CLAUDE.md` section 4: every admin action goes to the immutable log."""

    async def test_creating_is_logged(self, db_session: AsyncSession) -> None:
        admin = await actor_with_role(db_session, Role.ADMIN)

        created = await service.create_benchmark(db_session, admin, band())

        entries = await AuditLogRepository(db_session).list_for_target(
            target_type="benchmark", target_id=str(created.id)
        )
        assert entries, "an admin write must reach the audit log"
        assert any(
            entry.action == AuditAction.BENCHMARK_CREATED.value for entry in entries
        )

    async def test_retiring_is_logged(self, db_session: AsyncSession) -> None:
        admin = await actor_with_role(db_session, Role.ADMIN)
        created = await service.create_benchmark(db_session, admin, band())

        await service.retire_benchmark(db_session, admin, created.id)

        entries = await AuditLogRepository(db_session).list_for_target(
            target_type="benchmark", target_id=str(created.id)
        )
        assert entries, "an admin write must reach the audit log"
        assert any(
            entry.action == AuditAction.BENCHMARK_RETIRED.value for entry in entries
        )


class TestTheFallbackChain:
    """Most specific first, and it says which rung it landed on."""

    async def test_an_exact_match_wins(self, db_session: AsyncSession) -> None:
        admin = await actor_with_role(db_session, Role.ADMIN)
        await service.create_benchmark(db_session, admin, band("logistics", "NG"))
        await service.create_benchmark(
            db_session, admin, band(ANY_SECTOR, GLOBAL_REGION)
        )

        match = await service.lookup_benchmark(
            db_session, sector="logistics", stage=Stage.SEED, metric=MARGIN, region="NG"
        )

        assert match is not None
        assert match.quality is MatchQuality.EXACT

    async def test_it_falls_back_to_the_same_sector_globally(
        self, db_session: AsyncSession
    ) -> None:
        admin = await actor_with_role(db_session, Role.ADMIN)
        await service.create_benchmark(
            db_session, admin, band("logistics", GLOBAL_REGION)
        )

        match = await service.lookup_benchmark(
            db_session, sector="logistics", stage=Stage.SEED, metric=MARGIN, region="NG"
        )

        assert match is not None
        assert match.quality is MatchQuality.REGION_FALLBACK

    async def test_it_falls_back_to_any_sector_in_the_region(
        self, db_session: AsyncSession
    ) -> None:
        admin = await actor_with_role(db_session, Role.ADMIN)
        await service.create_benchmark(db_session, admin, band(ANY_SECTOR, "NG"))

        match = await service.lookup_benchmark(
            db_session,
            sector="something-nobody-curated",
            stage=Stage.SEED,
            metric=MARGIN,
            region="NG",
        )

        assert match is not None
        assert match.quality is MatchQuality.SECTOR_FALLBACK

    async def test_the_last_rung_is_broad(self, db_session: AsyncSession) -> None:
        admin = await actor_with_role(db_session, Role.ADMIN)
        await service.create_benchmark(
            db_session, admin, band(ANY_SECTOR, GLOBAL_REGION)
        )

        match = await service.lookup_benchmark(
            db_session,
            sector="novel-sector",
            stage=Stage.SEED,
            metric=MARGIN,
            region="KE",
        )

        assert match is not None
        assert match.quality is MatchQuality.BROAD

    async def test_nothing_matching_returns_none(
        self, db_session: AsyncSession
    ) -> None:
        """The rubric must read this as "no comparison", never as "average"."""
        match = await service.lookup_benchmark(
            db_session,
            sector="unseeded",
            stage=Stage.GROWTH,
            metric=MARGIN,
            region="ZZ",
        )

        assert match is None

    async def test_stage_is_never_widened(self, db_session: AsyncSession) -> None:
        """A seed band tells you nothing about a growth company, so a stage
        miss is a miss -- not a fallback."""
        admin = await actor_with_role(db_session, Role.ADMIN)
        await service.create_benchmark(
            db_session, admin, band(ANY_SECTOR, GLOBAL_REGION, stage=Stage.SEED)
        )

        match = await service.lookup_benchmark(
            db_session,
            sector="logistics",
            stage=Stage.GROWTH,
            metric=MARGIN,
            region="NG",
        )

        assert match is None

    async def test_a_retired_band_is_not_matched(
        self, db_session: AsyncSession
    ) -> None:
        admin = await actor_with_role(db_session, Role.ADMIN)
        created = await service.create_benchmark(db_session, admin, band())
        await service.retire_benchmark(db_session, admin, created.id)

        match = await service.lookup_benchmark(
            db_session, sector="logistics", stage=Stage.SEED, metric=MARGIN, region="NG"
        )

        assert match is None

    async def test_sector_matching_ignores_case(self, db_session: AsyncSession) -> None:
        """Otherwise "Fintech" and "fintech" are two cells and a curated band
        is missed silently."""
        admin = await actor_with_role(db_session, Role.ADMIN)
        await service.create_benchmark(db_session, admin, band("FinTech", "NG"))

        match = await service.lookup_benchmark(
            db_session, sector="fintech", stage=Stage.SEED, metric=MARGIN, region="NG"
        )

        assert match is not None
        assert match.quality is MatchQuality.EXACT


class TestBandIntegrity:
    async def test_out_of_order_quartiles_are_refused(
        self, db_session: AsyncSession
    ) -> None:
        """A p50 below p25 is a typo that would invert every verdict scored
        against it."""
        admin = await actor_with_role(db_session, Role.ADMIN)

        with pytest.raises(InvalidRequestError):
            await service.create_benchmark(
                db_session,
                admin,
                band(p25=Decimal("50"), p50=Decimal("20"), p75=Decimal("60")),
            )

    async def test_one_band_per_cell(self, db_session: AsyncSession) -> None:
        """Two rows for one key would let query order decide a verdict."""
        admin = await actor_with_role(db_session, Role.ADMIN)
        await service.create_benchmark(db_session, admin, band())

        with pytest.raises(ConflictError):
            await service.create_benchmark(db_session, admin, band())

    async def test_the_key_cannot_be_moved(self, db_session: AsyncSession) -> None:
        """Sector, stage, metric and region say which cell a band is. Editing
        one relocates a curated band somewhere nobody curated it for.

        Enforced in the service, not only by the request schema -- this is a
        public function T2.6 reaches with a plain dict.
        """
        admin = await actor_with_role(db_session, Role.ADMIN)
        created = await service.create_benchmark(db_session, admin, band())

        with pytest.raises(InvalidRequestError):
            await service.update_benchmark(
                db_session, admin, created.id, {"region": "KE"}
            )

        assert created.region == "NG", "the row must be untouched"

    async def test_values_can_still_be_revised(self, db_session: AsyncSession) -> None:
        admin = await actor_with_role(db_session, Role.ADMIN)
        created = await service.create_benchmark(db_session, admin, band())

        updated = await service.update_benchmark(
            db_session, admin, created.id, {"p50": Decimal("29")}
        )

        assert updated.p50 == Decimal("29")

    async def test_provenance_survives_the_round_trip(
        self, db_session: AsyncSession
    ) -> None:
        """A founder told their margin is bottom-quartile is entitled to know
        against what, gathered when (`CLAUDE.md` section 5)."""
        admin = await actor_with_role(db_session, Role.ADMIN)

        created = await service.create_benchmark(db_session, admin, band())

        assert created.source == "SACI portfolio review, Q2 2026"
        assert created.as_of_date == date(2026, 6, 30)
