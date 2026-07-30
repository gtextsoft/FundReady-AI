"""Intake ORM tables.

Layer: **models** (ARCHITECTURE.md section 3) -- SQLAlchemy table definitions
only. Every schema change also requires an Alembic migration under
`migrations/`; the database is never hand-edited.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.intake.fields import Stage


class StartupProfile(Base):
    """A founder's business, as the audit engine will read it.

    Two storage shapes, for two different jobs:

    * **Indexed columns** for the handful of values other subsystems filter and
      join on -- benchmark lookup is keyed by sector x stage x region (T2.3) and
      investor discovery filters on the same (T4.3). Those need to be real
      columns.
    * **A JSONB document** for everything else, where each field carries its own
      `source` and `confidence`. Extraction (T2.4) fills these in from uploaded
      documents with varying certainty, and the canonical field list is still
      provisional (see `fields.py`), so putting them in columns would mean a
      migration every time the list changed.

    Nothing here is required. A half-complete profile is the normal state, not
    an error: the PRD's flow is that the founder starts, the AI extracts more,
    and `missing_fields` reports the gap. Completeness is the *audit's* gate,
    not the profile's.

    **Sector is free text.** DECISIONS.md D11 requires accepting sectors that do
    not exist yet, so it cannot be an enum.
    """

    __tablename__ = "startup_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # One profile per founder in v1, enforced by the unique index. The PRD's
    # flows are all singular ("the founder's business"); if a founder ever needs
    # several, dropping the constraint is the whole change.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    name: Mapped[str | None] = mapped_column(String(200))
    sector: Mapped[str | None] = mapped_column(String(120), index=True)
    stage: Mapped[Stage | None] = mapped_column(
        SAEnum(
            Stage,
            native_enum=False,
            length=16,
            name="startup_stage",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        index=True,
    )
    # ISO 3166-1 alpha-2. Region-aware benchmarks and per-country programme
    # matching both key off this (T5.1, T5.2).
    country: Mapped[str | None] = mapped_column(String(2), index=True)
    # ISO 4217. Money elsewhere is integer minor units, which is meaningless
    # without knowing the currency (AGENTS.md section 4).
    currency: Mapped[str | None] = mapped_column(String(3))

    # {field_name: {"value": ..., "source": ..., "confidence": ..., ...}}
    fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # `onupdate` is a Python callable, not `func.now()`. A server-side
    # onupdate leaves the ORM not knowing the new value, so it expires the
    # attribute and reading it back for a response triggers lazy IO --
    # which under async SQLAlchemy raises MissingGreenlet. Computing it here
    # means the value is sent as a parameter and already known.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        # No name or sector: __repr__ ends up in logs, and this is a founder's
        # confidential business data.
        return f"<StartupProfile {self.id} owner={self.owner_id}>"
