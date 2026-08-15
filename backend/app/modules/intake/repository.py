"""Intake data access.

Layer: **repository** (ARCHITECTURE.md section 3) -- database access only.
Queries in, models/data out. No business rules, no authorization decisions.

**Nothing here filters by owner.** That is not an oversight: ownership is an
authorization decision and belongs in the service (DECISIONS.md D13), where it
is applied uniformly and tested in one place. A repository that quietly scoped
its own queries would make the service's checks look redundant, and the first
query someone added without the filter would be the hole.
"""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.intake.documents import DocumentKind
from app.modules.intake.fields import Stage
from app.modules.intake.models import (
    CompanyVerificationStatus,
    Document,
    StartupProfile,
)


class StartupProfileRepository:
    """Read and write startup profiles."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, profile_id: uuid.UUID) -> StartupProfile | None:
        return await self._session.get(StartupProfile, profile_id)

    async def get_for_owner(self, owner_id: uuid.UUID) -> StartupProfile | None:
        result: StartupProfile | None = await self._session.scalar(
            select(StartupProfile).where(StartupProfile.owner_id == owner_id)
        )
        return result

    async def create(
        self,
        *,
        owner_id: uuid.UUID,
        name: str | None = None,
        sector: str | None = None,
        stage: Stage | None = None,
        country: str | None = None,
        currency: str | None = None,
        fields: dict[str, Any] | None = None,
    ) -> StartupProfile:
        profile = StartupProfile(
            owner_id=owner_id,
            name=name,
            sector=sector,
            stage=stage,
            country=country,
            currency=currency,
            fields=fields or {},
        )
        self._session.add(profile)
        await self._session.flush()
        return profile

    async def list_all(
        self,
        *,
        verification: CompanyVerificationStatus | None,
        q: str | None = None,
        country: str | None = None,
        sector: str | None = None,
        stage: Stage | None = None,
        published: bool | None = None,
        startup_id: uuid.UUID | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[StartupProfile], int]:
        statement = select(StartupProfile)
        if startup_id is not None:
            statement = statement.where(StartupProfile.id == startup_id)
        if verification is not None:
            statement = statement.where(
                StartupProfile.company_verification_status == verification
            )
        if country:
            statement = statement.where(
                StartupProfile.country == country.strip().upper()
            )
        if sector:
            statement = statement.where(
                func.lower(StartupProfile.sector) == sector.strip().lower()
            )
        if stage is not None:
            statement = statement.where(StartupProfile.stage == stage)
        if published is not None:
            statement = statement.where(StartupProfile.investor_visible.is_(published))
        if q and q.strip():
            needle = f"%{q.strip().lower()}%"
            statement = statement.where(
                func.lower(func.coalesce(StartupProfile.name, "")).like(needle)
                | func.lower(func.coalesce(StartupProfile.sector, "")).like(needle)
                | func.lower(func.coalesce(StartupProfile.country, "")).like(needle)
            )
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(statement.subquery())
            )
            or 0
        )
        rows = list(
            await self._session.scalars(
                statement.order_by(StartupProfile.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return rows, total


class DocumentRepository:
    """Read and write document metadata. The bytes are in R2, not here."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, document_id: uuid.UUID) -> Document | None:
        return await self._session.get(Document, document_id)

    async def list_for_startup(self, startup_id: uuid.UUID) -> list[Document]:
        """Newest first -- the founder's last upload is the one they are
        looking for. Unfiltered by owner: that is the service's decision
        (DECISIONS.md D13), and the caller has already been authorised against
        the startup this belongs to."""
        result = await self._session.scalars(
            select(Document)
            .where(Document.startup_id == startup_id)
            .order_by(Document.created_at.desc())
        )
        return list(result)

    async def create(
        self,
        *,
        document_id: uuid.UUID,
        owner_id: uuid.UUID,
        startup_id: uuid.UUID,
        kind: DocumentKind,
        filename: str,
        storage_key: str,
    ) -> Document:
        document = Document(
            id=document_id,
            owner_id=owner_id,
            startup_id=startup_id,
            kind=kind,
            filename=filename,
            storage_key=storage_key,
        )
        self._session.add(document)
        await self._session.flush()
        return document
