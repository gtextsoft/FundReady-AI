"""Structured-output JSON schemas for model responses.

Audits, dimension scores, and evidence assessments are validated against these
before anything downstream sees them. Invalid output is rejected and retried;
raw model text never reaches a client (CLAUDE.md section 5).

This module holds the *shared vocabulary* every model response is built from --
the citation, the sufficiency verdict, the base class that forbids unknown
fields. The rubric's own dimensions and the report shape are not here: they are
defined by the rubric version that produces them (T2.6/T2.7), so that adding a
dimension is a rubric change rather than an edit to this file.

Three rules the types below exist to enforce:

* **Unknown fields are an error, not a shrug.** `StructuredOutput` sets
  `extra="forbid"`, which does double duty: it rejects a response carrying a
  field we did not ask for, and it is what makes the wire schema come out with
  `additionalProperties: false` -- the form the API requires for a strict
  `json_schema` output format.
* **A verdict without citations is not a verdict.** `EvidenceBacked` requires at
  least one `Citation`, so "the model asserted it" cannot pass for "the
  submission supports it" (CLAUDE.md section 5).
* **Thin data has to read as thin.** `DataSufficiency` has no default. A model
  that cannot support a conclusion must say `INSUFFICIENT_DATA` rather than
  quietly returning a confident-looking score, and the absence of a default
  means it cannot omit the field to avoid the question.

Implemented in TASKS.md T2.1.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StructuredOutput(BaseModel):
    """Base for every schema the model is asked to fill in.

    `extra="forbid"` is load-bearing twice over -- see the module docstring.
    Never relax it on a subclass to "be tolerant" of a model that adds a field;
    a response we did not ask for is a response we have not reasoned about.
    """

    model_config = ConfigDict(extra="forbid")


class DataSufficiency(StrEnum):
    """Whether the submitted data can support a conclusion at all.

    Deliberately separate from any score. A dimension can be well-evidenced and
    score badly, or be unscoreable because the founder submitted nothing on it,
    and collapsing those two into a low score is precisely the false verdict
    CLAUDE.md section 5 forbids.
    """

    SUFFICIENT = "sufficient"
    """Enough evidence to state a conclusion."""

    PROVISIONAL = "provisional"
    """Partial evidence: a conclusion is offered but must be labelled provisional."""

    INSUFFICIENT_DATA = "insufficient_data"
    """Not enough evidence. No conclusion may be drawn, and none may be implied."""


class Citation(StructuredOutput):
    """A pointer from a claim back to the submitted data that supports it.

    `source_id` identifies the submission -- a document id or a Startup Profile
    field name -- and `quote` is the span the model actually relied on. Both are
    required: an id alone cannot be checked by a human reviewer, and a quote
    alone cannot be traced back to what the founder submitted.
    """

    source_id: str = Field(
        min_length=1,
        description="Document id or Startup Profile field name the claim rests on.",
    )
    quote: str = Field(
        min_length=1,
        description="The exact span of submitted data supporting the claim.",
    )


class EvidenceBacked(StructuredOutput):
    """Base for any model output that asserts something about a startup.

    Subclasses inherit the two fields that make an assertion checkable.

    **The citation requirement is conditional, and deliberately so.** A claim
    must cite the data it rests on -- but `INSUFFICIENT_DATA` is precisely the
    answer given when there is no such data, and a hard `min_length=1` on the
    field would leave the model two ways out: invent a citation, or invent a
    conclusion. Both are the failure CLAUDE.md section 5 exists to prevent. So
    the rule is enforced where it is actually true: *conclusions* need
    citations, "I cannot tell from this" does not.

    Enforcement happens when the response is validated, not in the wire schema.
    The API's `json_schema` format cannot express "required only when another
    field has a particular value", and the SDK demotes unsupported JSON-Schema
    keywords to prose in the field description anyway (see `ai.client`). A
    violation therefore surfaces as a validation failure and is retried, which
    is the correct outcome either way.
    """

    sufficiency: DataSufficiency = Field(
        description=(
            "Whether the submitted data supports a conclusion. Use "
            "'insufficient_data' rather than guessing; a missing conclusion is "
            "correct, a fabricated one is not."
        )
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description=(
            "The submitted data this rests on. Required unless sufficiency is "
            "'insufficient_data'. Cite what you actually used, not everything "
            "you were given."
        ),
    )

    @model_validator(mode="after")
    def _conclusions_must_cite(self) -> "EvidenceBacked":
        """Reject a conclusion that cites nothing."""
        if self.sufficiency is not DataSufficiency.INSUFFICIENT_DATA and not (
            self.citations
        ):
            raise ValueError(
                f"sufficiency '{self.sufficiency.value}' asserts a conclusion, "
                "so at least one citation is required"
            )
        return self
