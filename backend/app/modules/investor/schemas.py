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
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.security import KycStatus
from app.modules.audit.models import AuditRun
from app.modules.audit.reports import VerdictSummary, summary_report
from app.modules.intake.fields import Stage
from app.modules.intake.models import StartupProfile
from app.modules.investor.models import InvestorProfile, ThesisReviewStatus

__all__ = [
    "AnalystChatRequest",
    "AnalystChatResponse",
    "DiscoveryFilters",
    "DiscoveryPage",
    "InvestorProfileResponse",
    "InvestorProfileUpdate",
    "InvestorReviewCard",
    "InvestorReviewPage",
    "StartupCard",
    "ThesisDecision",
    "WatchlistResponse",
]


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


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
        stored = run.report if isinstance(run.report, dict) else {}
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


class InvestorProfileUpdate(BaseModel):
    """Thesis fields an investor may write. Review status is server-set."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "firm": "Sahel Capital",
                "investor_type": "vc",
                "country": "NG",
                "linkedin_url": "https://www.linkedin.com/in/example",
                "thesis_sectors": ["fintech"],
                "thesis_stages": ["seed"],
                "thesis_geographies": ["NG", "KE"],
                "ticket_min_minor": 5000000,
                "ticket_max_minor": 25000000,
                "ticket_currency": "USD",
                "risk_notes": "Prefer revenue-generating B2B.",
            }
        },
    )

    firm: str | None = Field(default=None, max_length=200)
    investor_type: str | None = Field(default=None, max_length=80)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    linkedin_url: str | None = Field(default=None, max_length=400)
    thesis_sectors: list[str] = Field(default_factory=list, max_length=20)
    thesis_stages: list[str] = Field(default_factory=list, max_length=10)
    thesis_geographies: list[str] = Field(default_factory=list, max_length=20)
    ticket_min_minor: int | None = Field(default=None, ge=0)
    ticket_max_minor: int | None = Field(default=None, ge=0)
    ticket_currency: str | None = Field(default=None, min_length=3, max_length=3)
    risk_notes: str | None = Field(default=None, max_length=2000)


class InvestorProfileResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "firm": "Sahel Capital",
                "investor_type": "vc",
                "country": "NG",
                "linkedin_url": None,
                "thesis_sectors": ["fintech"],
                "thesis_stages": ["seed"],
                "thesis_geographies": ["NG"],
                "ticket_min_minor": 5000000,
                "ticket_max_minor": 25000000,
                "ticket_currency": "USD",
                "risk_notes": None,
                "kyc_status": "none",
                "review_status": "in_review",
            }
        },
    )

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
    kyc_status: KycStatus
    review_status: ThesisReviewStatus

    @classmethod
    def of(
        cls, row: InvestorProfile, kyc_status: KycStatus
    ) -> "InvestorProfileResponse":
        return cls(
            firm=row.firm,
            investor_type=row.investor_type,
            country=row.country,
            linkedin_url=row.linkedin_url,
            thesis_sectors=_string_list(row.thesis_sectors),
            thesis_stages=_string_list(row.thesis_stages),
            thesis_geographies=_string_list(row.thesis_geographies),
            ticket_min_minor=row.ticket_min_minor,
            ticket_max_minor=row.ticket_max_minor,
            ticket_currency=row.ticket_currency,
            risk_notes=row.risk_notes,
            kyc_status=kyc_status,
            review_status=row.review_status,
        )


class InvestorReviewCard(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "user_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
                "email": "lp@example.com",
                "first_name": "Ada",
                "last_name": "Okoye",
                "firm": "Sahel Capital",
                "investor_type": "vc",
                "country": "NG",
                "linkedin_url": None,
                "thesis_sectors": ["fintech"],
                "thesis_stages": ["seed"],
                "thesis_geographies": ["NG"],
                "risk_notes": None,
                "review_status": "in_review",
                "updated_at": "2026-08-15T12:00:00Z",
            }
        },
    )

    user_id: UUID
    email: str
    first_name: str | None
    last_name: str | None
    firm: str | None
    investor_type: str | None
    country: str | None
    linkedin_url: str | None
    thesis_sectors: list[str]
    thesis_stages: list[str]
    thesis_geographies: list[str]
    risk_notes: str | None
    review_status: ThesisReviewStatus
    updated_at: datetime | None


class InvestorReviewPage(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {"items": [], "total": 0, "limit": 20, "offset": 0}
        },
    )

    items: list[InvestorReviewCard]
    total: int
    limit: int
    offset: int


class ThesisDecision(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": {"accept": True}},
    )

    accept: bool


class WatchlistResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "startup_ids": ["5f2b1c9e-0000-4000-8000-000000000001"],
                "watching": True,
            }
        },
    )

    startup_ids: list[UUID]
    watching: bool | None = None


class AnalystChatRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "message": "What stage is this company?",
                "history": [],
            }
        },
    )

    message: str = Field(min_length=1, max_length=2000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=10)


class AnalystChatResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "reply": "The card lists stage as seed.",
                "citations": [{"kind": "card", "ref": "stage"}],
            }
        },
    )

    reply: str
    citations: list[dict[str, str]] = Field(default_factory=list)
