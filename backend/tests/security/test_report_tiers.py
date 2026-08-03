"""Report tiers: what each caller is entitled to see (T4.2).

`CLAUDE.md` section 4 makes two promises about this, and they are the two most
consequential promises in the product:

* An investor gets **summary only**. The full report is revealed by a SACI admin
  action and by nothing else.
* Tiers are enforced **server-side, per tier, via dedicated serializers** --
  never by trusting a client to hide fields.

So these tests are not about shape. They are about leakage, and they are written
to fail the way a breach actually happens: not "the model has the wrong fields"
but "a founder's private text came out of an endpoint an investor can reach".

**The technique is sentinels.** Every founder-only string in the fixture is a
unique marker, and the investor assertions search the *entire serialized
response* for every one of them. A test that instead listed the expected keys
would pass a serializer that nested the whole stored document under a new key,
which is exactly the sort of change that gets made in a hurry.
"""

import json
from decimal import Decimal

import pytest

from app.ai.schemas import Citation, DataSufficiency
from app.modules.audit.consistency import Finding, FindingCode, Severity
from app.modules.audit.reports import (
    AdminReport,
    FounderReport,
    SummaryReport,
    admin_report,
    founder_report,
    summary_report,
)
from app.modules.audit.rubric.v1 import Dimension, DimensionScore
from app.modules.audit.schemas import report_to_storage
from app.modules.audit.synthesis import synthesise

# Every one of these is text only the founder and SACI may ever see. Each is
# unique so a failure names precisely which field escaped.
RATIONALE_SENTINEL = "SENTINEL-rationale-runway-is-two-months"
FINDING_MESSAGE_SENTINEL = "SENTINEL-message-your-churn-looks-mistyped"
FINDING_DETAIL_SENTINEL = "SENTINEL-detail-engineer-facing-comparison"
ACTION_SENTINEL = "SENTINEL-action-obtain-a-signed-ip-assignment"
DIMENSION_SENTINEL = "unit_economics"

FOUNDER_ONLY_SENTINELS = (
    FINDING_MESSAGE_SENTINEL,
    FINDING_DETAIL_SENTINEL,
    ACTION_SENTINEL,
)


def _stored() -> dict:
    """A realistic stored report, built the way the pipeline builds one."""
    scores = [
        DimensionScore(
            dimension=dimension,
            score=55,
            rationale="scored for the fixture",
            sufficiency=DataSufficiency.SUFFICIENT,
            citations=[Citation(source_id="startup_profile", quote="revenue")],
            unmet_criteria=[ACTION_SENTINEL] if dimension is Dimension.TEAM else [],
        )
        for dimension in Dimension
    ]
    report = synthesise(
        rubric_version="v1",
        scores=scores,
        data_integrity_score=Decimal(85),
        findings=[
            Finding(
                code=FindingCode.CHURN_IMPLAUSIBLY_LOW,
                severity=Severity.LIKELY,
                fields=("monthly_churn_percent",),
                message=FINDING_MESSAGE_SENTINEL,
                detail=FINDING_DETAIL_SENTINEL,
            )
        ],
    )
    stored = report_to_storage(report)
    # The verdict rationale is generated text; overwrite it so it is traceable.
    stored["fundability"]["rationale"] = RATIONALE_SENTINEL
    stored["saleability"]["rationale"] = RATIONALE_SENTINEL
    return stored


def _json(model: SummaryReport | FounderReport | AdminReport) -> str:
    return json.dumps(model.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# The investor wall
# ---------------------------------------------------------------------------


class TestInvestorSummaryLeaksNothing:
    """The single most important test in this file."""

    @pytest.mark.parametrize("sentinel", FOUNDER_ONLY_SENTINELS)
    def test_no_founder_only_text_survives_anywhere_in_the_response(
        self, sentinel: str
    ) -> None:
        """Searches the whole serialized document, not a list of keys.

        A serializer that nested the full stored report under some new key
        would satisfy a key-based assertion and breach this one.
        """
        assert sentinel not in _json(summary_report(_stored()))

    def test_the_verdict_rationale_does_not_survive(self) -> None:
        """The rationale is the diagnosis, and the diagnosis is what SACI brokers.

        Split out from the parametrised cases because it is the one an author in
        a hurry is most likely to add back -- it reads like a harmless sentence
        about the score rather than like a private finding.
        """
        assert RATIONALE_SENTINEL not in _json(summary_report(_stored()))

    def test_the_action_plan_is_absent_entirely(self) -> None:
        """Not empty -- absent. An itemised list of everything still wrong with
        the company is the full report under a different name."""
        assert not hasattr(summary_report(_stored()), "action_plan")

    def test_findings_are_absent_entirely(self) -> None:
        assert not hasattr(summary_report(_stored()), "findings")

    def test_the_integrity_score_is_absent(self) -> None:
        """It reads as a number and functions as "how far do we believe them"."""
        assert not hasattr(summary_report(_stored()), "data_integrity_score")

    def test_which_dimensions_were_assessed_is_absent(self) -> None:
        """The shape of what could not be assessed is itself diagnostic."""
        payload = _json(summary_report(_stored()))

        assert DIMENSION_SENTINEL not in payload

    def test_the_summary_model_cannot_be_given_a_rationale(self) -> None:
        """Structural, not behavioural: the class has no such field.

        This is why the tiers are three models rather than one model plus an
        `exclude=` argument. An exclude someone forgets is a breach; a class
        that cannot hold the attribute is not.
        """
        with pytest.raises(ValueError):
            SummaryReport(
                rubric_version="v1",
                fundability={"scope": "fundability", "level": "ready", "score": 80},
                saleability={"scope": "saleability", "level": "ready", "score": 80},
                rationale=RATIONALE_SENTINEL,
            )

    def test_a_key_added_to_storage_later_does_not_appear(self) -> None:
        """The allow-list guarantee.

        Storage is written by this codebase and read back as an untyped dict, so
        the risk is a *future* key riding into a narrow tier. `_verdict_summary`
        picks the keys it wants rather than dropping the ones it knows about,
        which makes the default for anything new "absent".
        """
        stored = _stored()
        stored["internal_note"] = "SENTINEL-saci-positioning-note"
        stored["fundability"]["internal_confidence"] = "SENTINEL-internal-confidence"

        payload = _json(summary_report(stored))

        assert "SENTINEL-saci-positioning-note" not in payload
        assert "SENTINEL-internal-confidence" not in payload

    def test_the_verdicts_do_come_through(self) -> None:
        """The wall has to let the actual product through, or it is just a wall."""
        summary = summary_report(_stored())

        assert summary.fundability.level
        assert summary.saleability.level
        assert summary.rubric_version == "v1"


# ---------------------------------------------------------------------------
# The founder tier
# ---------------------------------------------------------------------------


class TestFounderSeesTheirOwnReport:
    def test_the_founder_gets_the_actionable_content(self) -> None:
        report = founder_report(_stored())
        payload = _json(report)

        assert RATIONALE_SENTINEL in payload
        assert FINDING_MESSAGE_SENTINEL in payload
        assert ACTION_SENTINEL in payload
        assert report.data_integrity_score == Decimal(85)

    def test_engineer_facing_detail_is_withheld(self) -> None:
        """`Finding` carries two texts for two audiences.

        `message` is written for the founder and assumes a mistake rather than
        deception. `detail` names the comparison that fired, for whoever is
        debugging. Showing the second to a founder is not a privacy breach -- it
        is their own data -- but it is internal wording that would read as an
        accusation, and section 4 draws the tier at what each audience is
        *served*, not at what is technically theirs.
        """
        assert FINDING_DETAIL_SENTINEL not in _json(founder_report(_stored()))

    def test_unevidenced_dimensions_come_through(self) -> None:
        """This list is what the client turns into "answer these next"."""
        report = founder_report(_stored())

        assert isinstance(report.fundability.unevidenced_dimensions, list)


# ---------------------------------------------------------------------------
# The SACI tier
# ---------------------------------------------------------------------------


class TestAdminSeesEverything:
    def test_nothing_is_withheld_from_saci(self) -> None:
        payload = _json(admin_report(_stored()))

        for sentinel in (*FOUNDER_ONLY_SENTINELS, RATIONALE_SENTINEL):
            assert sentinel in payload, f"admin tier withheld {sentinel}"


# ---------------------------------------------------------------------------
# The one that must never read as a rejection
# ---------------------------------------------------------------------------


def test_insufficient_data_carries_a_null_score_in_every_tier() -> None:
    """`insufficient_data` is an absence, not a failure.

    A tier that coerced the missing score to `0` would render as "scored zero
    out of a hundred" on a client -- telling a founder they failed an assessment
    that was never made. `Verdict.score` is `None` for exactly this reason and
    the serializers must carry the `None` through rather than default it.
    """
    stored = _stored()
    for scope in ("fundability", "saleability"):
        stored[scope]["level"] = "insufficient_data"
        stored[scope]["score"] = None
        stored[scope]["sufficiency"] = "insufficient_data"

    assert summary_report(stored).fundability.score is None
    assert founder_report(stored).fundability.score is None
    assert admin_report(stored).saleability.score is None
