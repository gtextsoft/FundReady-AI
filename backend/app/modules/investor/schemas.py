"""Investor request/response schemas (T4.3).

Layer: **schemas** (ARCHITECTURE.md section 3) -- Pydantic request and response
models, including the per-tier response serializers (summary vs full). Unknown
or extra fields are rejected. Tier filtering lives here and is enforced by the
service, never by the client (DECISIONS.md D8).

**`StartupCard` is a summary-tier object and every field on it was chosen.**
This is the first place a founder's business is shown to somebody who is not
them, so the test to apply to any new field is not "would this be useful to an
investor" -- it would be; the full report would be extremely useful -- but
"would SACI hand this over before brokering the introduction". See the class
docstring for what is excluded and why.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.audit.models import AuditRun
from app.modules.audit.reports import VerdictSummary, summary_report
from app.modules.intake.fields import Stage
from app.modules.intake.models import StartupProfile

__all__ = [
    "DiscoveryFilters",
    "DiscoveryPage",
    "IdentitySessionResponse",
    "InvestorProfileResponse",
    "InvestorProfileUpsert",
    "StartupCard",
    "WatchlistResponse",
]


@dataclass(frozen=True, slots=True)
class DiscoveryFilters:
    """What an investor may narrow discovery by.

    Exactly the indexed columns on `StartupProfile`, which is not a
    coincidence: `intake.models` says those columns exist because benchmark
    lookup and investor discovery both filter on them.
    """

    sector: str | None = None
    stage: Stage | None = None
    country: str | None = None


class StartupCard(BaseModel):
    """One discoverable startup, at summary tier.

    **What is deliberately absent**, beyond everything `SummaryReport` already
    excludes:

    * **The founder's identity and contact details.** SACI brokers the
      introduction; a card carrying an email is a card that routes around it.
    * **Every profile field.** Revenue, costs, runway, customer counts, churn
      -- the submitted figures are the founder's confidential business data.
      An investor gets the *verdict*, which is what the audit is for; the
      figures behind it come with the brokered conversation.
    * **`data_integrity_score` and findings**, for the reason `SummaryReport`
      gives: "these numbers do not add up" is a diagnosis, and the diagnosis is
      what SACI brokers.

    What remains is the four discovery columns and the two verdicts -- enough
    to decide whether to ask for an introduction, and not enough to skip one.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "startup_id": "5f2b1c9e-0000-4000-8000-000000000001",
                "name": "Kanmi Pay",
                "sector": "fintech",
                "stage": "seed",
                "country": "NG",
                "audit_run_id": "5f2b1c9e-0000-4000-8000-000000000002",
                "rubric_version": "v1",
                "fundability": {
                    "scope": "fundability",
                    "level": "ready",
                    "score": 78,
                },
                "saleability": {
                    "scope": "saleability",
                    "level": "not_yet",
                    "score": 61,
                },
                "published_at": "2026-08-03T12:00:00Z",
            }
        },
    )

    startup_id: UUID
    name: str | None = None
    sector: str | None = None
    stage: Stage | None = None
    country: str | None = None

    audit_run_id: UUID = Field(
        description=(
            "The run this card was built from. Quote it when expressing "
            "interest: a founder who re-audits produces a new verdict, and a "
            "reveal names the exact run that was disclosed."
        )
    )
    rubric_version: str
    fundability: VerdictSummary
    saleability: VerdictSummary
    published_at: datetime | None = Field(
        default=None, description="When the founder opted in to discovery."
    )

    @classmethod
    def of(cls, profile: StartupProfile, run: AuditRun) -> "StartupCard":
        """Build a card from a profile and the audit behind it.

        The report is passed through `summary_report` rather than read field by
        field, so this card can never carry more of a verdict than the investor
        tier allows -- there is exactly one place that decision is made.
        """
        stored: dict[str, Any] = run.report or {}
        summary = summary_report(stored)
        return cls(
            startup_id=profile.id,
            name=profile.name,
            sector=profile.sector,
            stage=profile.stage,
            country=profile.country,
            audit_run_id=run.id,
            rubric_version=summary.rubric_version,
            fundability=summary.fundability,
            saleability=summary.saleability,
            published_at=profile.published_at,
        )


class DiscoveryPage(BaseModel):
    """One page of discovery results.

    Carries `total` because `CLAUDE.md` section 6 asks for consistent list
    conventions and no client can render "page N of M" without it. Noted in
    TASKS.md as the shape the other list endpoints should be retrofitted to.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {"items": [], "total": 0, "limit": 20, "offset": 0}
        },
    )

    items: list[StartupCard]
    total: int = Field(description="Total matching startups, ignoring pagination.")
    limit: int
    offset: int


class InvestorProfileUpsert(BaseModel):
    """Thesis + firm details an investor may set before or after KYC."""

    model_config = ConfigDict(extra="forbid")

    firm: str | None = Field(default=None, max_length=200)
    investor_type: str | None = Field(default=None, max_length=64)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    linkedin_url: str | None = Field(default=None, max_length=500)
    thesis_sectors: list[str] = Field(default_factory=list, max_length=20)
    thesis_stages: list[Stage] = Field(default_factory=list, max_length=10)
    thesis_geographies: list[str] = Field(default_factory=list, max_length=20)
    ticket_min_minor: int | None = Field(default=None, ge=0)
    ticket_max_minor: int | None = Field(default=None, ge=0)
    ticket_currency: str | None = Field(default=None, min_length=3, max_length=3)
    risk_notes: str | None = Field(default=None, max_length=2000)


class InvestorProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    firm: str | None = None
    investor_type: str | None = None
    country: str | None = None
    linkedin_url: str | None = None
    thesis_sectors: list[str] = Field(default_factory=list)
    thesis_stages: list[str] = Field(default_factory=list)
    thesis_geographies: list[str] = Field(default_factory=list)
    ticket_min_minor: int | None = None
    ticket_max_minor: int | None = None
    ticket_currency: str | None = None
    risk_notes: str | None = None
    kyc_status: str


class IdentitySessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    session_id: str
    kyc_status: str


class WatchlistResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    startup_ids: list[UUID]
