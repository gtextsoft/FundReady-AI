"""Per-tier report serializers (TASKS.md T4.2).

Layer: **schema** (ARCHITECTURE.md section 3). Pure: no I/O, no session.

`CLAUDE.md` section 4 is unambiguous about this file's job: *"Report tiers are
enforced server-side, per tier, via dedicated serializers -- never by trusting
the client to hide fields."* These are those serializers, and they are the only
supported way a stored report reaches a response.

**The whole report is written to the database and filtered on the way out.**
`schemas.report_to_storage` stores everything the run concluded, because a
verdict a founder disputes has to be reconstructable exactly as it was issued.
That makes *this* module the only wall between an investor and a founder's full
audit, which is why the three tiers are three separate Pydantic models rather
than one model with optional fields. A model that cannot declare a field cannot
leak it by accident -- an `exclude=` argument someone forgets is a breach, a
class that has no such attribute is not.

**Three tiers, and what each is entitled to:**

* **Founder** -- their own full, actionable report: both verdicts with the
  reasoning, the integrity score, every finding written for them, and the action
  plan. Not `Finding.detail`, which is engineer-facing text written for whoever
  is debugging a support conversation.
* **Investor** -- *summary only*: the two verdict levels and their scores. No
  rationale, no findings, no action plan, no dimension breakdown. See
  `SummaryReport` for why each of those is excluded rather than merely omitted.
* **SACI admin** -- everything, including `detail`. The reveal to an investor is
  an admin action recorded in the immutable audit log (T4.6); it is not a tier.

**An investor never reaches a founder's report through ownership.** They have no
entitlement to the object at all -- `core.ownership.owned_or_404` exempts admins
and deliberately does not exempt investors. The summary is served through
discovery, over startups that have opted in, and the full report only ever
through a SACI reveal.
"""

from decimal import Decimal
from enum import StrEnum
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ActionItemView",
    "AdminReport",
    "FinderView",
    "FounderReport",
    "ReportTier",
    "SummaryReport",
    "VerdictDetail",
    "VerdictSummary",
    "admin_report",
    "founder_report",
    "summary_report",
]


class ReportTier(StrEnum):
    """Who is being served. One value per serializer, and no default.

    No default on purpose: a caller that forgets to say which tier it wants
    should fail to compile a request rather than quietly receive the widest one.
    """

    FOUNDER = "founder"
    INVESTOR = "investor"
    ADMIN = "admin"


class _Strict(BaseModel):
    """Forbids unknown fields on the way *out* as well as in.

    The stored JSONB is written by this codebase, but it is still read back as
    an untyped `dict`. `extra="forbid"` means a key added to storage later
    cannot ride into a narrow tier's response just because the constructor was
    handed the whole document.
    """

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------


class VerdictSummary(_Strict):
    """What an investor may see of one verdict: the answer, and nothing else."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"scope": "fundability", "level": "not_yet", "score": 58}
        }
    )

    scope: str
    level: str = Field(
        description=(
            "`ready`, `not_yet`, `provisional`, or `insufficient_data`. "
            "**`insufficient_data` is an absence, not a failure** -- it must "
            "never be rendered as 'not fundable'."
        )
    )
    score: int | None = Field(
        default=None,
        description="0-100, or null when no score was formed (`insufficient_data`).",
    )


class VerdictDetail(VerdictSummary):
    """What a founder may see: the answer plus why, and what is still thin."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "scope": "fundability",
                "level": "provisional",
                "score": 58,
                "sufficiency": "provisional",
                "rationale": (
                    "Provisional: scored 58 out of 100 on the evidence "
                    "available, but some areas are still thin. Filling the gaps "
                    "below could move this in either direction."
                ),
                "evidenced_dimensions": ["financial_health", "unit_economics"],
                "unevidenced_dimensions": ["market_opportunity", "scalability"],
            }
        }
    )

    sufficiency: str
    rationale: str = Field(
        description="Founder-facing. Says what the verdict is and what would change it."
    )
    evidenced_dimensions: list[str]
    unevidenced_dimensions: list[str] = Field(
        description=(
            "Dimensions with nothing to score. **This is the list to drive the "
            "next questions from** -- filling these is what moves a verdict off "
            "`provisional`."
        )
    )


# ---------------------------------------------------------------------------
# Findings and actions
# ---------------------------------------------------------------------------


class FinderView(_Strict):
    """One thing that does not add up, as the founder is shown it.

    `detail` is deliberately absent. `consistency.Finding` carries two texts for
    two audiences -- `message` is written for the founder and never accusatory,
    `detail` names the comparison that fired for whoever is debugging. Only the
    admin tier gets the second.
    """

    code: str
    severity: str
    fields: list[str]
    message: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "churn_implausibly_low",
                "severity": "likely",
                "fields": ["monthly_churn_percent", "active_customers"],
                "message": (
                    "Your monthly churn is under 0.1%, which at your customer "
                    "count would mean fewer than one customer leaves per month. "
                    "If you meant 2% rather than 0.02, please enter it as 2."
                ),
            }
        }
    )


class AdminFindingView(FinderView):
    """The founder's view plus the engineer-facing comparison."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "more_founders_than_team",
                "severity": "certain",
                "fields": ["team_size", "founder_count"],
                "message": ("You have listed more founders than total team members."),
                "detail": "founder_count > team_size",
            }
        }
    )

    detail: str


class ActionItemView(_Strict):
    """One thing the founder can do to improve the verdict.

    Ordered worst-first by the synthesis stage, and unassessable dimensions
    sort ahead of low-scoring ones: "we could not assess this" is cheaper to fix
    *and* it is what blocks the verdict.
    """

    dimension: str
    action: str
    dimension_score: int | None = None
    is_priority: bool = False
    """Whether to show this in the short list before "show everything".

    The first live audit produced 44 items. Every one is still in this array --
    nothing is truncated server-side -- but a founder shown 44 acts on none of
    them. Expect at most five true, each from a different dimension.

    Defaults to `False` so a report stored before this field existed still
    deserialises; those reports simply have no short list.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "dimension": "legal_and_ip",
                "action": (
                    "Obtain a signed IP assignment from the contractor who "
                    "built the dispatch app."
                ),
                "dimension_score": 40,
            }
        }
    )


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


class SummaryReport(_Strict):
    """The investor tier. Two verdicts and the rubric they came from.

    **Everything excluded here is excluded deliberately, not for brevity:**

    * `rationale` -- prose explaining the weaknesses behind a score. That is the
      diagnosis, and the diagnosis is what SACI brokers.
    * `findings` -- a list of the founder's figures that do not add up. Handing
      that to an investor unbrokered is the full report by another name.
    * `action_plan` -- everything the company still has to fix, itemised.
    * `data_integrity_score` -- reads as a number and functions as "how much do
      we believe them", which is a judgement the summary tier does not carry.
    * `evidenced_dimensions` / `unevidenced_dimensions` -- the shape of what was
      and was not assessed is itself diagnostic.

    If a field is being considered for this model, `CLAUDE.md` section 4's rule
    applies: *if unsure whether a field is safe, exclude it and ask.*
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rubric_version": "v1",
                "fundability": {
                    "scope": "fundability",
                    "level": "not_yet",
                    "score": 58,
                },
                "saleability": {
                    "scope": "saleability",
                    "level": "not_yet",
                    "score": 45,
                },
            }
        }
    )

    rubric_version: str
    fundability: VerdictSummary
    saleability: VerdictSummary


class FounderReport(_Strict):
    """The founder tier: their own audit, in full, written for them."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rubric_version": "v1",
                "data_integrity_score": "85",
                "fundability": {
                    "scope": "fundability",
                    "level": "provisional",
                    "score": 58,
                    "sufficiency": "provisional",
                    "rationale": (
                        "Provisional: scored 58 out of 100 on the "
                        "evidence available, but some areas are still thin."
                    ),
                    "evidenced_dimensions": ["financial_health"],
                    "unevidenced_dimensions": ["market_opportunity"],
                },
                "saleability": {
                    "scope": "saleability",
                    "level": "provisional",
                    "score": 58,
                    "sufficiency": "provisional",
                    "rationale": (
                        "Provisional: scored 58 out of 100 on the "
                        "evidence available, but some areas are still thin."
                    ),
                    "evidenced_dimensions": ["financial_health"],
                    "unevidenced_dimensions": ["market_opportunity"],
                },
                "findings": [
                    {
                        "code": "churn_implausibly_low",
                        "severity": "likely",
                        "fields": ["monthly_churn_percent"],
                        "message": (
                            "Your monthly churn is under 0.1%. If you "
                            "meant 2% rather than 0.02, enter it as 2."
                        ),
                    }
                ],
                "action_plan": [
                    {
                        "dimension": "legal_and_ip",
                        "action": (
                            "Obtain a signed IP assignment from the "
                            "contractor who built the dispatch app."
                        ),
                        "dimension_score": 40,
                    }
                ],
            }
        }
    )

    rubric_version: str
    data_integrity_score: Decimal = Field(
        description=(
            "0-100. Below 50 no verdict is formed at all and both levels read "
            "`insufficient_data` -- the figures disagree with each other too "
            "much to score."
        )
    )
    fundability: VerdictDetail
    saleability: VerdictDetail
    findings: list[FinderView]
    action_plan: list[ActionItemView]


class AdminReport(_Strict):
    """The SACI tier: everything, including the engineer-facing detail."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rubric_version": "v1",
                "data_integrity_score": "85",
                "fundability": {
                    "scope": "fundability",
                    "level": "provisional",
                    "score": 58,
                    "sufficiency": "provisional",
                    "rationale": (
                        "Provisional: scored 58 out of 100 on the "
                        "evidence available, but some areas are still thin."
                    ),
                    "evidenced_dimensions": ["financial_health"],
                    "unevidenced_dimensions": ["market_opportunity"],
                },
                "saleability": {
                    "scope": "saleability",
                    "level": "provisional",
                    "score": 58,
                    "sufficiency": "provisional",
                    "rationale": (
                        "Provisional: scored 58 out of 100 on the "
                        "evidence available, but some areas are still thin."
                    ),
                    "evidenced_dimensions": ["financial_health"],
                    "unevidenced_dimensions": ["market_opportunity"],
                },
                "findings": [
                    {
                        "code": "more_founders_than_team",
                        "severity": "certain",
                        "fields": ["team_size", "founder_count"],
                        "message": ("You have listed more founders than team members."),
                        "detail": "founder_count > team_size",
                    }
                ],
                "action_plan": [
                    {
                        "dimension": "legal_and_ip",
                        "action": (
                            "Obtain a signed IP assignment from the "
                            "contractor who built the dispatch app."
                        ),
                        "dimension_score": 40,
                    }
                ],
            }
        }
    )

    rubric_version: str
    data_integrity_score: Decimal
    fundability: VerdictDetail
    saleability: VerdictDetail
    findings: list[AdminFindingView]
    action_plan: list[ActionItemView]


# ---------------------------------------------------------------------------
# Building them
# ---------------------------------------------------------------------------

_SUMMARY_VERDICT_KEYS: Final = ("scope", "level", "score")


def _verdict_summary(raw: dict[str, Any]) -> VerdictSummary:
    """Pick only the summary keys, rather than dropping the ones we know about.

    An allow-list, not a deny-list. A key added to the stored verdict later is
    then absent from the summary by default -- with a deny-list it would appear
    in every investor response until somebody noticed.
    """
    picked: dict[str, Any] = {key: raw.get(key) for key in _SUMMARY_VERDICT_KEYS}
    return VerdictSummary.model_validate(picked)


def _verdict_detail(raw: dict[str, Any]) -> VerdictDetail:
    return VerdictDetail(
        scope=raw["scope"],
        level=raw["level"],
        score=raw.get("score"),
        sufficiency=raw["sufficiency"],
        rationale=raw["rationale"],
        evidenced_dimensions=list(raw.get("evidenced_dimensions", [])),
        unevidenced_dimensions=list(raw.get("unevidenced_dimensions", [])),
    )


def _actions(stored: dict[str, Any]) -> list[ActionItemView]:
    return [
        ActionItemView(
            dimension=item["dimension"],
            action=item["action"],
            dimension_score=item.get("dimension_score"),
            # `.get` with a default: reports stored before this field existed
            # are still served rather than raising on a missing key.
            is_priority=bool(item.get("is_priority", False)),
        )
        for item in stored.get("action_plan", [])
    ]


def summary_report(stored: dict[str, Any]) -> SummaryReport:
    """The investor view of a stored report. See `SummaryReport`."""
    return SummaryReport(
        rubric_version=stored["rubric_version"],
        fundability=_verdict_summary(stored["fundability"]),
        saleability=_verdict_summary(stored["saleability"]),
    )


def founder_report(stored: dict[str, Any]) -> FounderReport:
    """The founder's own report, in full, minus engineer-facing detail."""
    return FounderReport(
        rubric_version=stored["rubric_version"],
        data_integrity_score=Decimal(str(stored["data_integrity_score"])),
        fundability=_verdict_detail(stored["fundability"]),
        saleability=_verdict_detail(stored["saleability"]),
        findings=[
            FinderView(
                code=finding["code"],
                severity=finding["severity"],
                fields=list(finding.get("fields", [])),
                message=finding["message"],
            )
            for finding in stored.get("findings", [])
        ],
        action_plan=_actions(stored),
    )


def admin_report(stored: dict[str, Any]) -> AdminReport:
    """Everything the run concluded. SACI only."""
    return AdminReport(
        rubric_version=stored["rubric_version"],
        data_integrity_score=Decimal(str(stored["data_integrity_score"])),
        fundability=_verdict_detail(stored["fundability"]),
        saleability=_verdict_detail(stored["saleability"]),
        findings=[
            AdminFindingView(
                code=finding["code"],
                severity=finding["severity"],
                fields=list(finding.get("fields", [])),
                message=finding["message"],
                detail=finding["detail"],
            )
            for finding in stored.get("findings", [])
        ],
        action_plan=_actions(stored),
    )
