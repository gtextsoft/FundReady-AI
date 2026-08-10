"""Mentor chat request/response schemas (T3.7)."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatTurn(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"role": "user", "content": "What should I fix first?"}]
        },
    )

    role: ChatRole
    content: str = Field(min_length=1, max_length=2000)


class MentorChatRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "message": "Explain my top gap in plain language.",
                    "history": [],
                }
            ]
        },
    )

    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=10)


class CitationKind(StrEnum):
    FINDING = "finding"
    TASK = "task"
    VERDICT = "verdict"
    PROFILE = "profile"


class MentorCitation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"kind": "finding", "ref": "finding:runway"}]
        },
    )

    kind: CitationKind
    ref: str = Field(min_length=1, max_length=120)


class MentorChatResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "reply": "Your biggest gap is runway evidence.",
                    "citations": [{"kind": "finding", "ref": "finding:runway"}],
                }
            ]
        },
    )

    reply: str
    citations: list[MentorCitation] = Field(default_factory=list)
