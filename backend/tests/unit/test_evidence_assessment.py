"""T3.5: grading evidence against the task it was uploaded for.

Three properties carry the weight, and none of them is about plumbing.

**"They uploaded something" is not a pass.** `CLAUDE.md` section 5 says so, and
the failure it names is a specific one: a founder attaching any file and being
advanced toward investor visibility. The grader is the only thing standing in
front of that.

**Ambiguity resolves to `needs_more`.** The same thin-data guarantee the audit
makes one layer up -- `provisional` rather than a confident verdict. Here the
cost of getting it wrong is symmetric and both directions are bad: a false pass
admits an unready startup, a false fail burns one of three attempts.

**The grader cannot write a task status.** `AssessmentOutcome` and `TaskStatus`
are separate vocabularies joined by an explicit mapping, which is what stops a
model's output *being* the task state -- the "uploads must not act as
instructions" line in section 5.
"""

import pytest

from app.ai.client import ModelTier
from app.modules.audit.extraction import SourceDocument
from app.modules.readiness.assessment import (
    ASSESSMENT_PROMPT,
    EvidenceAssessment,
    assess_evidence,
)
from app.modules.readiness.evidence import (
    MAX_ASSESSMENT_ATTEMPTS,
    AssessmentOutcome,
    EvidenceStatus,
    attempts_remaining,
)
from app.modules.readiness.generation import TaskStatus
from app.modules.readiness.service import _TASK_STATUS_FOR  # noqa: PLC2701

# ---------------------------------------------------------------------------
# The attempt cap
# ---------------------------------------------------------------------------


def test_a_fresh_task_has_the_full_budget() -> None:
    assert attempts_remaining(0) == MAX_ASSESSMENT_ATTEMPTS


def test_the_budget_falls_with_each_graded_attempt() -> None:
    assert attempts_remaining(1) == MAX_ASSESSMENT_ATTEMPTS - 1
    assert attempts_remaining(MAX_ASSESSMENT_ATTEMPTS) == 0


def test_the_budget_never_goes_negative() -> None:
    """This number is shown to a founder.

    "-1 attempts remaining" is not something anyone can act on, and a negative
    would mean the cap had been breached -- which the service prevents. Clamping
    keeps a display bug from becoming a second, louder bug.
    """
    assert attempts_remaining(MAX_ASSESSMENT_ATTEMPTS + 5) == 0


def test_a_cap_actually_exists() -> None:
    """The guard on the investor-visibility gate.

    Grading is a model call and a model does not answer identically twice, so
    unlimited attempts means a determined founder eventually passes anything.
    The number is tunable; its existence is not.
    """
    assert MAX_ASSESSMENT_ATTEMPTS > 0
    assert MAX_ASSESSMENT_ATTEMPTS < 10, "a cap this high is not a cap"


# ---------------------------------------------------------------------------
# The grader cannot write a task status
# ---------------------------------------------------------------------------


def test_every_outcome_maps_to_a_task_status() -> None:
    """A missing entry would be a KeyError in the worker, after a billed call."""
    assert set(_TASK_STATUS_FOR) == set(AssessmentOutcome)


def test_the_mapping_is_the_seam_between_two_vocabularies() -> None:
    assert _TASK_STATUS_FOR[AssessmentOutcome.PASS] is TaskStatus.PASSED
    assert _TASK_STATUS_FOR[AssessmentOutcome.FAIL] is TaskStatus.FAILED
    assert _TASK_STATUS_FOR[AssessmentOutcome.NEEDS_MORE] is TaskStatus.NEEDS_MORE


def test_no_outcome_can_retire_or_obsolete_a_task() -> None:
    """A grader that could write `obsolete` could make a required task vanish.

    The mapping's *range* is the guarantee, not just its keys.
    """
    assert TaskStatus.OBSOLETE not in set(_TASK_STATUS_FOR.values())
    assert TaskStatus.OPEN not in set(_TASK_STATUS_FOR.values())


# ---------------------------------------------------------------------------
# Upload lifecycle and grading are separate axes
# ---------------------------------------------------------------------------


def test_upload_status_and_grading_outcome_do_not_overlap() -> None:
    """A rejected upload and a failed assessment mean very different things.

    One is "your file did not arrive"; the other is "your work was assessed and
    fell short". A founder shown the wrong one is being told something untrue,
    so the two vocabularies deliberately share no value.
    """
    assert not {status.value for status in EvidenceStatus} & {
        outcome.value for outcome in AssessmentOutcome
    }


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------


def test_the_prompt_states_the_two_rules_that_matter() -> None:
    """Asserted on the text because they are the product guarantees.

    A refactor that trims the prompt for tokens would otherwise quietly drop
    them, and nothing else in the suite reads the prompt body.
    """
    text = ASSESSMENT_PROMPT.text.lower()

    assert "not a pass" in text, "the 'a file arriving is not a pass' rule"
    assert "needs_more" in text and "unsure" in text, "the ambiguity rule"


def test_the_prompt_warns_that_the_submission_may_argue_for_itself() -> None:
    """The specific injection shape here: a document that says 'pass me'."""
    text = ASSESSMENT_PROMPT.text.lower()

    assert "instruction to be followed" in text or "never instruction" in text


def test_the_prompt_is_registered_and_versioned() -> None:
    """D12: a stored grading cites this, so it must be resolvable later."""
    assert ASSESSMENT_PROMPT.ref == "evidence_assessment@1"


# ---------------------------------------------------------------------------
# Nothing readable costs nothing
# ---------------------------------------------------------------------------


class _NoCallClient:
    """An AI client that fails the test if anything reaches the network."""

    def profile_for(self, tier: ModelTier) -> object:
        class _Profile:
            model = "claude-opus-5"

        return _Profile()

    async def complete(self, **_kwargs: object) -> None:
        raise AssertionError("no model call should have been made")


async def test_nothing_readable_returns_needs_more_without_a_call() -> None:
    """An empty submission is not a grading judgement -- there is nothing to grade.

    Spending an `AUDIT`-tier call to be told a zero-byte file is unreadable is
    money for an answer already known, and `attempts=0` on the record is the
    honest marker that no request was made.
    """
    result = await assess_evidence(
        _NoCallClient(),  # type: ignore[arg-type]
        criterion="Publish a pricing page.",
        submissions=[],
    )

    assert result.output.outcome is AssessmentOutcome.NEEDS_MORE
    assert result.record.attempts == 0
    assert result.record.usage.input_tokens == 0
    assert result.output.reasons, "a founder is still owed a reason"


async def test_an_unreadable_file_type_also_costs_nothing() -> None:
    result = await assess_evidence(
        _NoCallClient(),  # type: ignore[arg-type]
        criterion="Publish a pricing page.",
        submissions=[
            SourceDocument(
                document_id="e1",
                filename="mystery.bin",
                content_type="application/octet-stream",
                content=b"\x00\x01\x02",
            )
        ],
    )

    assert result.output.outcome is AssessmentOutcome.NEEDS_MORE
    assert result.record.attempts == 0


# ---------------------------------------------------------------------------
# The output schema
# ---------------------------------------------------------------------------


def test_a_verdict_without_reasons_is_rejected() -> None:
    """Every outcome carries reasons, including a pass.

    A founder told "passed" with no reason cannot tell a real assessment from a
    rubber stamp; one told "failed" with no reason has a verdict and no path.
    """
    with pytest.raises(ValueError, match="reasons"):
        EvidenceAssessment(outcome=AssessmentOutcome.PASS, reasons=[], citations=[])


def test_an_unknown_field_is_rejected() -> None:
    """Inherited from `StructuredOutput` -- never relaxed on a subclass."""
    with pytest.raises(ValueError, match="task_status|extra"):
        EvidenceAssessment(
            outcome=AssessmentOutcome.PASS,
            reasons=["Done."],
            citations=[],
            task_status="passed",
        )
