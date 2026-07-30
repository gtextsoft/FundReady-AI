"""The canonical Startup Profile field set.

**Provisional.** `saci-audit-platform-backend-spec.md` is named as a source of
truth by `CLAUDE.md` sections 1 and 10 but is not in the repository, so this
list is derived from what the rest of the PRD demonstrably needs rather than
copied from a specification:

* benchmark lookup (T2.3) is keyed by *sector x stage x metric x region*
* `finance.py` (T2.2) computes margins, burn, runway and CAC/LTV **in code**
  (DECISIONS.md D9), so the profile stores raw inputs and never derived figures
* investor discovery (T4.3) filters on sector, stage and geography

Correcting it is cheap on purpose: everything except the five indexed columns
lives in a JSONB document, so adding, renaming, or removing a field here costs
no migration.

A registry rather than typed columns because extraction (T2.4) fills these in
from documents with varying confidence, and a half-known profile is the normal
case, not an error.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class FieldSource(StrEnum):
    """Where a field's value came from.

    Recorded per field because the audit has to cite its evidence
    (CLAUDE.md section 5) and a founder's own claim is not the same kind of
    input as a figure read out of their financials.
    """

    FOUNDER = "founder"
    DOCUMENT = "document"
    INFERRED = "inferred"


class Stage(StrEnum):
    """Funding stage.

    A bounded vocabulary, unlike sector: benchmarks are keyed by stage, so it
    has to match across startups to be comparable at all.
    """

    IDEA = "idea"
    PRE_SEED = "pre_seed"
    SEED = "seed"
    SERIES_A = "series_a"
    SERIES_B_PLUS = "series_b_plus"
    GROWTH = "growth"


class FieldKind(StrEnum):
    """How a field's value is validated and interpreted."""

    TEXT = "text"
    INTEGER = "integer"
    MONEY_MINOR = "money_minor"  # integer minor units (AGENTS.md section 4)
    PERCENT = "percent"  # 0-100
    YEAR = "year"
    BOOLEAN = "boolean"


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One field a Startup Profile may carry."""

    name: str
    kind: FieldKind
    description: str
    required_for_audit: bool = False


# Sector is deliberately absent from any enum: DECISIONS.md D11 requires the
# platform to accept sectors that do not exist yet, so it is free text and the
# rubric's adaptive layer deals with novelty.
PROFILE_FIELDS: Final[tuple[FieldSpec, ...]] = (
    # -- Business ----------------------------------------------------------
    FieldSpec(
        "description",
        FieldKind.TEXT,
        "What the business does, in the founder's words.",
        required_for_audit=True,
    ),
    FieldSpec(
        "business_model",
        FieldKind.TEXT,
        "How it makes money (subscription, marketplace, licence, ...).",
        required_for_audit=True,
    ),
    FieldSpec("website", FieldKind.TEXT, "Public website, if any."),
    FieldSpec("founded_year", FieldKind.YEAR, "Year the business started trading."),
    # -- Team --------------------------------------------------------------
    FieldSpec(
        "team_size",
        FieldKind.INTEGER,
        "Total people working on the business, including founders.",
        required_for_audit=True,
    ),
    FieldSpec("founder_count", FieldKind.INTEGER, "Number of founders."),
    FieldSpec(
        "founders_full_time",
        FieldKind.INTEGER,
        "How many founders work on this full time.",
    ),
    # -- Financial inputs. Raw only: every ratio is computed in finance.py --
    FieldSpec(
        "monthly_revenue_minor",
        FieldKind.MONEY_MINOR,
        "Revenue in the most recent full month.",
        required_for_audit=True,
    ),
    FieldSpec(
        "monthly_costs_minor",
        FieldKind.MONEY_MINOR,
        "Total operating costs in the most recent full month.",
        required_for_audit=True,
    ),
    FieldSpec(
        "cash_on_hand_minor",
        FieldKind.MONEY_MINOR,
        "Cash available now. With monthly costs, this gives runway.",
        required_for_audit=True,
    ),
    FieldSpec(
        "cost_of_revenue_minor",
        FieldKind.MONEY_MINOR,
        "Direct cost of delivering revenue, for gross margin.",
    ),
    FieldSpec(
        "last_12m_revenue_minor",
        FieldKind.MONEY_MINOR,
        "Revenue over the trailing twelve months.",
    ),
    # -- Traction ----------------------------------------------------------
    FieldSpec("active_customers", FieldKind.INTEGER, "Paying customers today."),
    FieldSpec("monthly_active_users", FieldKind.INTEGER, "Monthly active users."),
    FieldSpec(
        "customer_acquisition_cost_minor",
        FieldKind.MONEY_MINOR,
        "Average cost to acquire one customer.",
    ),
    FieldSpec(
        "average_revenue_per_customer_minor",
        FieldKind.MONEY_MINOR,
        "Average revenue per customer per month.",
    ),
    FieldSpec(
        "monthly_churn_percent",
        FieldKind.PERCENT,
        "Share of customers lost per month.",
    ),
    # -- Funding -----------------------------------------------------------
    FieldSpec("total_raised_minor", FieldKind.MONEY_MINOR, "Capital raised to date."),
    FieldSpec(
        "current_raise_target_minor",
        FieldKind.MONEY_MINOR,
        "Amount currently being raised, if any.",
    ),
    FieldSpec("cap_table_summary", FieldKind.TEXT, "Who owns what, in summary."),
    # -- Saleability (PRD: fundable *and* saleable) -------------------------
    FieldSpec(
        "ip_owned",
        FieldKind.BOOLEAN,
        "Whether the business owns its core intellectual property.",
    ),
    FieldSpec(
        "key_person_dependency",
        FieldKind.TEXT,
        "What breaks if a specific person leaves.",
    ),
    FieldSpec(
        "contracts_transferable",
        FieldKind.BOOLEAN,
        "Whether customer contracts survive a change of ownership.",
    ),
)

FIELDS_BY_NAME: Final[dict[str, FieldSpec]] = {f.name: f for f in PROFILE_FIELDS}

# The indexed columns. Required for an audit too, but they are not in the JSONB
# document, so completeness has to consider both.
REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "name",
    "sector",
    "stage",
    "country",
    "currency",
)

REQUIRED_FIELDS: Final[frozenset[str]] = frozenset(
    f.name for f in PROFILE_FIELDS if f.required_for_audit
)
