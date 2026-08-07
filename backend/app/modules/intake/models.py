"""Intake ORM tables.

Layer: **models** (ARCHITECTURE.md section 3) -- SQLAlchemy table definitions
only. Every schema change also requires an Alembic migration under
`migrations/`; the database is never hand-edited.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.intake.documents import DocumentKind, DocumentStatus, ScanStatus
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

    # -- Investor visibility (T4.3) ------------------------------------------
    #
    # **Opt-in, defaulting to false, and never derived.** It would be cheaper to
    # treat "has a succeeded audit" as discoverable and skip this column
    # entirely -- and it would publish a founder's confidential business data
    # because they used the product. Running an audit is not consent to be shown
    # to investors; those are two different decisions and a founder makes them
    # separately.
    #
    # The publish action checks that an audit has succeeded, so this cannot be
    # set on an unaudited shell. When the readiness gate lands (T3.6) it adds
    # "and the required tasks are complete" to that same check -- this column
    # does not change shape, only the guard in front of it gets stricter.
    investor_visible: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """When the founder last opted in. Cleared on unpublish, so the column also
    answers "has this ever been discoverable" for a support conversation."""

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


class Document(Base):
    """A file a founder uploaded about their business.

    The **bytes live in R2, never here** (`fundready-prd.md` §7). This row is
    the metadata and the permission record: it says who owns the file, where it
    sits, and whether it is fit to be read yet.

    `owner_id` is stored alongside `startup_id` rather than reached through a
    join. That is deliberate: it lets `core.ownership.owned_or_404` decide
    access on this table with the same call it uses everywhere else, instead of
    a bespoke rule that loads the profile first. One ownership rule, one place
    (`DECISIONS.md` D13). It is safe to denormalise because a document cannot
    change hands -- there is no transfer flow, and one profile per founder.

    A row exists **before** the file does. Upload is: create this row `pending`,
    hand the client a signed URL, and only mark it `ready` once the object is
    confirmed present and acceptable. A row stuck at `pending` means the client
    never finished, which is ordinary and needs no cleanup path in v1.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    startup_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("startup_profiles.id", ondelete="CASCADE"), index=True
    )

    kind: Mapped[DocumentKind] = mapped_column(
        SAEnum(
            DocumentKind,
            native_enum=False,
            length=32,
            name="document_kind",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        index=True,
    )

    # Display text only. It is echoed back to the founder and used for the
    # download filename -- it is never a path component (see `core.storage`).
    filename: Mapped[str] = mapped_column(String(255))

    # Where the object sits in the bucket. Server-generated, so it is stable
    # even if the founder renames the file.
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)

    # Both are what **R2 reported** after the upload, not what the client
    # claimed when asking for the URL. Null until the upload is confirmed.
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)

    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(
            DocumentStatus,
            native_enum=False,
            length=16,
            name="document_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=DocumentStatus.PENDING,
        index=True,
    )
    scan_status: Mapped[ScanStatus] = mapped_column(
        SAEnum(
            ScanStatus,
            native_enum=False,
            length=16,
            name="document_scan_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=ScanStatus.PENDING,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        # No filename: a deck is often named after the company, and __repr__
        # reaches logs.
        return f"<Document {self.id} owner={self.owner_id} {self.status.value}>"
