"""Structured output the mentor model must return."""

from enum import StrEnum

from pydantic import Field

from app.ai.schemas import StructuredOutput


class MentorCitationKind(StrEnum):
    FINDING = "finding"
    TASK = "task"
    VERDICT = "verdict"
    PROFILE = "profile"


class MentorCitationOut(StructuredOutput):
    kind: MentorCitationKind
    ref: str = Field(
        min_length=1,
        max_length=120,
        description="Finding code, task dimension, verdict scope, or profile field.",
    )


class MentorReplyOut(StructuredOutput):
    """Schema-validated mentor answer — never free text past the client."""

    reply: str = Field(
        min_length=1,
        max_length=4000,
        description="Answer grounded only in the provided context.",
    )
    citations: list[MentorCitationOut] = Field(default_factory=list)
