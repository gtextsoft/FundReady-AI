"""Audit request/response schemas.

Layer: **schemas** (ARCHITECTURE.md section 3) -- Pydantic request and response
models, including the per-tier response serializers (summary vs full). Unknown
or extra fields are rejected. Tier filtering lives here and is enforced by the
service, never by the client (DECISIONS.md D8).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.audit.benchmarks import BenchmarkMetric, MatchQuality, Stage
from app.modules.audit.runs import AuditStatus

__all__ = [
    "AuditRunResponse",
    "BenchmarkCreate",
    "BenchmarkMetric",
    "BenchmarkResponse",
    "BenchmarkUpdate",
    "MatchQuality",
    "Stage",
    "report_to_storage",
]

BENCHMARK_ID_EXAMPLE = "1f0c9a2b-7d34-4e51-9a6f-2c8b3d4e5f60"

_EXAMPLE: dict[str, Any] = {
    "sector": "last-mile delivery",
    "stage": "seed",
    "metric": "gross_margin_percent",
    "region": "NG",
    "p25": "18.0000",
    "p50": "27.5000",
    "p75": "36.0000",
    "sample_size": 42,
    "source": "SACI portfolio review, Q2 2026",
    "as_of_date": "2026-06-30",
}


class _Band(BaseModel):
    """Quartile ordering, checked wherever a band is supplied."""

    @model_validator(mode="after")
    def _quartiles_are_ordered(self) -> "_Band":
        p25 = getattr(self, "p25", None)
        p50 = getattr(self, "p50", None)
        p75 = getattr(self, "p75", None)
        supplied = [value for value in (p25, p50, p75) if value is not None]
        if len(supplied) == 3 and not p25 <= p50 <= p75:  # type: ignore[operator]
            raise ValueError("quartiles must be ordered: p25 <= p50 <= p75")
        return self


class BenchmarkCreate(_Band):
    """Add one peer-group band.

    The key -- sector, stage, metric, region -- identifies the cell. Sector and
    region accept `*` for "any", which is what makes the last rung of the
    lookup fallback chain possible.
    """

    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [_EXAMPLE]}
    )

    sector: str = Field(
        max_length=120,
        description=(
            "Free text, matched case-insensitively. `*` for a band that "
            "applies to any sector."
        ),
    )
    stage: Stage = Field(
        description=(
            "Matched **exactly** at lookup -- a seed band never serves a "
            "growth company."
        )
    )
    metric: BenchmarkMetric = Field(
        description=(
            "Which figure this bands. Absolute-currency figures are absent by "
            "design: the platform does no FX conversion, so only dimensionless "
            "ratios and month counts are comparable across regions."
        )
    )
    region: str = Field(
        min_length=1,
        max_length=2,
        description="ISO 3166-1 alpha-2, or `*` for global.",
    )

    p25: Decimal = Field(description="Lower quartile.")
    p50: Decimal = Field(description="Median.")
    p75: Decimal = Field(description="Upper quartile.")

    sample_size: int | None = Field(
        default=None, ge=1, description="How many companies the band came from."
    )
    source: str = Field(
        min_length=1,
        max_length=300,
        description=(
            "Where these figures came from. **Required** -- a verdict cites "
            "its evidence, and a benchmark with no provenance cannot be cited."
        ),
    )
    as_of_date: date = Field(
        description=(
            "When the data was gathered. **Required** -- benchmarks go stale, "
            "and a date makes that visible rather than silent."
        )
    )


class BenchmarkUpdate(_Band):
    """Revise a band's values or provenance.

    The key is **not** editable. Sector, stage, metric, and region say which
    cell this is; moving them would silently relocate a band to a place nobody
    curated it for. Retire the row and create the right one instead.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"p50": "29.0000", "source": "SACI portfolio review, Q3 2026"}]
        },
    )

    p25: Decimal | None = None
    p50: Decimal | None = None
    p75: Decimal | None = None
    sample_size: int | None = Field(default=None, ge=1)
    source: str | None = Field(default=None, min_length=1, max_length=300)
    as_of_date: date | None = None


class BenchmarkResponse(BaseModel):
    """A stored band, as an admin sees it."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": BENCHMARK_ID_EXAMPLE,
                    **_EXAMPLE,
                    "higher_is_better": True,
                    "is_active": True,
                    "created_at": "2026-07-30T09:00:00Z",
                    "updated_at": "2026-07-30T09:00:00Z",
                }
            ]
        },
    )

    id: uuid.UUID
    sector: str
    stage: Stage
    metric: BenchmarkMetric
    region: str
    p25: Decimal
    p50: Decimal
    p75: Decimal
    sample_size: int | None
    source: str
    as_of_date: date
    is_active: bool = Field(
        description=(
            "Retired bands stay readable so past audits remain explainable, "
            "but lookup ignores them."
        )
    )
    created_at: datetime
    updated_at: datetime

    higher_is_better: bool = Field(
        description=(
            "Whether a larger value is the better one. Derived from the "
            "metric, not stored -- being above p75 is excellent for gross "
            "margin and poor for CAC payback."
        )
    )

    @classmethod
    def of(cls, benchmark: Any) -> "BenchmarkResponse":
        """Serialise, attaching the metric's direction."""
        from app.modules.audit.benchmarks import higher_is_better

        return cls(
            id=benchmark.id,
            sector=benchmark.sector,
            stage=benchmark.stage,
            metric=benchmark.metric,
            region=benchmark.region,
            p25=benchmark.p25,
            p50=benchmark.p50,
            p75=benchmark.p75,
            sample_size=benchmark.sample_size,
            source=benchmark.source,
            as_of_date=benchmark.as_of_date,
            is_active=benchmark.is_active,
            created_at=benchmark.created_at,
            updated_at=benchmark.updated_at,
            higher_is_better=higher_is_better(benchmark.metric),
        )


# ---------------------------------------------------------------------------
# Audit runs (T2.8)
# ---------------------------------------------------------------------------

AUDIT_RUN_ID_EXAMPLE = "9c4d1e77-3b2a-4f80-8d61-5a7e9f0c1b23"


class AuditRunResponse(BaseModel):
    """One audit run's lifecycle -- **status only, never the report**.

    This is the polling shape the mobile client reads while an audit runs, and
    the boundary matters: `CLAUDE.md` section 4 requires report content to go
    through a per-tier serializer, and this endpoint is reachable by the founder
    the moment the run is created. Adding a `report` field here would route the
    full internal report around the tier rules for every caller at once. The
    report is served separately once its serializer exists (T4.2 for the
    investor tier, T2.7's founder view alongside it).

    `error_message` is founder-facing and deliberately thin. Whatever an
    engineer needs to debug the failure is in the log line for the run, not in a
    column the API hands back.
    """

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": AUDIT_RUN_ID_EXAMPLE,
                    "startup_id": "3f2b1a09-8c7d-4e65-b4a3-1d2c3b4a5e6f",
                    "status": "running",
                    "rubric_version": "v1",
                    "attempts": 1,
                    "error_code": None,
                    "error_message": None,
                    "created_at": "2026-08-02T09:00:00Z",
                    "started_at": "2026-08-02T09:00:04Z",
                    "completed_at": None,
                }
            ]
        },
    )

    id: uuid.UUID
    startup_id: uuid.UUID
    status: AuditStatus = Field(
        description=(
            "`queued` and `running` mean keep polling. `succeeded` and `failed` "
            "are terminal for this attempt; a failed run may be retried and "
            "reuses the same id rather than creating a second one."
        )
    )
    rubric_version: str = Field(
        description=(
            "The rubric this run was scored against. Recorded so a past verdict "
            "stays explainable after the rubric moves on."
        )
    )
    attempts: int = Field(description="How many times a worker has picked this run up.")
    error_code: str | None = Field(
        default=None,
        description=(
            "Stable code when `status` is `failed`. Branch on this, never on "
            "the message."
        ),
    )
    error_message: str | None = Field(
        default=None, description="Founder-safe explanation when `status` is `failed`."
    )
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


def report_to_storage(report: Any) -> dict[str, Any]:
    """An `AuditReport` as the JSONB column stores it.

    Whole, not filtered. The column holds everything the run concluded because a
    verdict a founder disputes has to be reconstructable exactly as it was
    issued; **tier filtering happens at the serializer that reads this back**,
    never on the way in (`CLAUDE.md` section 4).

    `Decimal` and enums are rendered as strings rather than floats: the integrity
    score is a `Decimal` for the same reason money is, and letting JSON coerce it
    to a float would make a stored verdict differ from the one that was computed.
    """
    return {
        "rubric_version": report.rubric_version,
        "data_integrity_score": str(report.data_integrity_score),
        "fundability": _verdict_to_storage(report.fundability),
        "saleability": _verdict_to_storage(report.saleability),
        "findings": [
            {
                "code": finding.code.value,
                "severity": finding.severity.value,
                "fields": list(finding.fields),
                "message": finding.message,
                "detail": finding.detail,
            }
            for finding in report.findings
        ],
        "action_plan": [
            {
                "dimension": item.dimension.value,
                "action": item.action,
                "dimension_score": item.dimension_score,
            }
            for item in report.action_plan
        ],
    }


def _verdict_to_storage(verdict: Any) -> dict[str, Any]:
    return {
        "scope": verdict.scope.value,
        "level": verdict.level.value,
        "score": verdict.score,
        "sufficiency": verdict.sufficiency.value,
        "evidenced_dimensions": [d.value for d in verdict.evidenced_dimensions],
        "unevidenced_dimensions": [d.value for d in verdict.unevidenced_dimensions],
        "rationale": verdict.rationale,
    }
