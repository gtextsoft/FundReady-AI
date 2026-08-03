"""T2.1: a call returns schema-valid JSON or fails cleanly.

The three failure modes are tested separately and asserted on *call count*, not
just on the exception type. Collapsing them would be the easy bug here: a
refusal that gets retried burns a second call for a guaranteed identical
answer, and a truncation that gets retried with the same budget truncates
again. "Fails cleanly" means the right exception after the right number of
attempts.

Security-critical paths first (CLAUDE.md section 7): no submitted values in an
error or a log line, and no conclusion without citations.
"""

import json
from typing import Any

import pytest
from pydantic import Field

from app.ai import caching
from app.ai import client as ai_client
from app.ai.client import (
    AiClient,
    AiInvalidOutputError,
    AiRefusalError,
    AiTruncatedError,
    ModelTier,
)
from app.ai.prompts import PromptVersion
from app.ai.schemas import Citation, DataSufficiency, EvidenceBacked, StructuredOutput
from app.core.config import Settings

PROMPT = PromptVersion(name="test_scoring", version=3, text="Score the thing.")


class Score(EvidenceBacked):
    """A stand-in for the real rubric output (T2.6)."""

    dimension: str
    value: int = Field(ge=0, le=100, description="0-100")


class Plain(StructuredOutput):
    answer: str


# ---------------------------------------------------------------------------
# Fake SDK client
# ---------------------------------------------------------------------------


class _Usage:
    def __init__(
        self,
        input_tokens: int = 10,
        output_tokens: int = 20,
        cache_creation_input_tokens: int = 5,
        cache_read_input_tokens: int = 100,
    ) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens


class _Block:
    def __init__(self, type_: str, text: str = "") -> None:
        self.type = type_
        self.text = text


class _Message:
    def __init__(
        self,
        text: str | None = None,
        *,
        stop_reason: str = "end_turn",
        thinking_first: bool = True,
    ) -> None:
        self.stop_reason = stop_reason
        self.usage = _Usage()
        # Thinking is on by default on the audit model, so a thinking block
        # ahead of the text block is the normal shape, not an edge case.
        self.content: list[_Block] = [_Block("thinking")] if thinking_first else []
        if text is not None:
            self.content.append(_Block("text", text))


class _FakeStream:
    def __init__(self, message: _Message) -> None:
        self._message = message

    async def __aenter__(self) -> "_FakeStream":
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    async def get_final_message(self) -> _Message:
        return self._message


class _FakeMessages:
    def __init__(self, responses: list[_Message]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    def stream(self, **kwargs: Any) -> _FakeStream:
        self.calls.append(kwargs)
        return _FakeStream(self._responses[len(self.calls) - 1])


class _FakeAnthropic:
    def __init__(self, responses: list[_Message]) -> None:
        self.messages = _FakeMessages(responses)


def _client(responses: list[_Message], **overrides: Any) -> tuple[AiClient, Any]:
    fake = _FakeAnthropic(responses)
    settings = Settings(**overrides)
    return AiClient(settings, client=fake), fake  # type: ignore[arg-type]


def _valid_score() -> str:
    return json.dumps(
        {
            "dimension": "traction",
            "value": 62,
            "sufficiency": "sufficient",
            "citations": [{"source_id": "deck.pdf", "quote": "MRR of 4.1m NGN"}],
        }
    )


async def _run(client: AiClient, schema: Any = Score) -> Any:
    return await client.complete(
        tier=ModelTier.AUDIT,
        prompt=PROMPT,
        schema=schema,
        system=caching.cached_system("rules"),
        messages=[{"role": "user", "content": "score it"}],
        user_id="user-1",
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_valid_response_is_returned_with_a_usage_record() -> None:
    client, fake = _client([_Message(_valid_score())])

    result = await _run(client)

    assert result.output.dimension == "traction"
    assert result.output.value == 62
    assert result.record.attempts == 1
    assert result.record.prompt_ref == "test_scoring@3"
    assert result.record.user_id == "user-1"
    assert len(fake.messages.calls) == 1


async def test_usage_record_keeps_the_cache_split() -> None:
    """Costing from `input_tokens` alone under-reports once caching works."""
    client, _ = _client([_Message(_valid_score())])

    usage = (await _run(client)).record.usage

    assert usage.input_tokens == 10
    assert usage.cache_read_input_tokens == 100
    assert usage.cache_creation_input_tokens == 5
    assert usage.total_input_tokens == 115


# ---------------------------------------------------------------------------
# Fails cleanly: three outcomes, three handlers
# ---------------------------------------------------------------------------


async def test_refusal_raises_and_is_not_retried() -> None:
    client, fake = _client([_Message(stop_reason="refusal")])

    with pytest.raises(AiRefusalError):
        await _run(client)

    assert len(fake.messages.calls) == 1


async def test_truncation_raises_and_is_not_retried() -> None:
    """A same-budget retry truncates identically and bills twice."""
    client, fake = _client([_Message('{"dimension": "trac', stop_reason="max_tokens")])

    with pytest.raises(AiTruncatedError):
        await _run(client)

    assert len(fake.messages.calls) == 1


# ---------------------------------------------------------------------------
# Failures are billed, so failures must report usage
#
# The three most expensive calls this client can make are all failures: a
# truncated audit runs to the full cap, and a mismatch retry bills twice. A
# budget (T5.5) fed only by successful `AiCallRecord`s would under-count
# precisely the spend it exists to cap.
# ---------------------------------------------------------------------------


async def test_refusal_reports_what_it_was_billed() -> None:
    client, _ = _client([_Message(stop_reason="refusal")])

    with pytest.raises(AiRefusalError) as caught:
        await _run(client)

    usage = caught.value.usage
    assert usage is not None
    assert usage.input_tokens == 10
    assert usage.total_input_tokens == 115


async def test_truncation_reports_what_it_was_billed() -> None:
    """The costliest single failure: output ran to the cap before it stopped."""
    client, _ = _client([_Message('{"dimension": "trac', stop_reason="max_tokens")])

    with pytest.raises(AiTruncatedError) as caught:
        await _run(client)

    usage = caught.value.usage
    assert usage is not None
    assert usage.output_tokens == 20


async def test_invalid_output_reports_both_attempts() -> None:
    """Two calls were billed, so the error must account for two."""
    client, fake = _client([_Message("not json"), _Message("still not json")])

    with pytest.raises(AiInvalidOutputError) as caught:
        await _run(client)

    assert len(fake.messages.calls) == 2
    usage = caught.value.usage
    assert usage is not None
    assert usage.input_tokens == 20
    assert usage.output_tokens == 40


async def test_a_refusal_on_the_retry_reports_the_first_attempt_too() -> None:
    """The regression this guards: `_call` only knows its own request's cost.

    Attempt 1 is billed and returns unparseable text; attempt 2 is billed and
    refused. Reporting only attempt 2 would halve the recorded spend.
    """
    client, fake = _client([_Message("not json"), _Message(stop_reason="refusal")])

    with pytest.raises(AiRefusalError) as caught:
        await _run(client)

    assert len(fake.messages.calls) == 2
    usage = caught.value.usage
    assert usage is not None
    assert usage.input_tokens == 20, "attempt 1's spend was dropped"
    assert usage.total_input_tokens == 230


async def test_mismatch_is_retried_once_then_raises() -> None:
    client, fake = _client([_Message('{"wrong": 1}'), _Message('{"wrong": 2}')])

    with pytest.raises(AiInvalidOutputError):
        await _run(client)

    assert len(fake.messages.calls) == 2


async def test_mismatch_then_valid_succeeds_and_sums_usage() -> None:
    client, fake = _client([_Message('{"wrong": 1}'), _Message(_valid_score())])

    result = await _run(client)

    assert result.output.value == 62
    assert result.record.attempts == 2
    assert len(fake.messages.calls) == 2
    # Both attempts were billed; the retry's cost is not lost.
    assert result.record.usage.output_tokens == 40


async def test_response_with_no_text_block_fails_cleanly() -> None:
    """Only a thinking block came back -- there is nothing to validate."""
    client, fake = _client([_Message(thinking_first=True)])

    with pytest.raises(AiInvalidOutputError):
        await _run(client)

    assert [block.type for block in fake.messages._responses[0].content] == ["thinking"]
    assert len(fake.messages.calls) == 1


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
async def test_blank_text_block_is_not_retried(blank: str) -> None:
    """An empty body gives the repair turn no field to name, so retrying it
    would spend a second call re-asking the identical question."""
    client, fake = _client([_Message(blank), _Message(_valid_score())])

    with pytest.raises(AiInvalidOutputError, match="no usable text block"):
        await _run(client)

    assert len(fake.messages.calls) == 1


# ---------------------------------------------------------------------------
# The repair turn
# ---------------------------------------------------------------------------


async def test_repair_turn_is_a_user_turn_not_a_prefill() -> None:
    """A last-assistant-turn prefill is a 400 on the audit model."""
    client, fake = _client([_Message('{"wrong": 1}'), _Message(_valid_score())])

    await _run(client)

    retry_messages = fake.messages.calls[1]["messages"]
    assert retry_messages[-1]["role"] == "user"
    assert all(message["role"] != "assistant" for message in retry_messages)


async def test_repair_turn_names_field_paths_but_no_values() -> None:
    """Model output can carry financial figures and PII (CLAUDE.md section 4)."""
    secret_figure = "418000000"
    bad = json.dumps({"dimension": "traction", "value": secret_figure})
    client, fake = _client([_Message(bad), _Message(_valid_score())])

    await _run(client)

    repair = fake.messages.calls[1]["messages"][-1]["content"]
    assert "value" in repair  # the field path is named
    assert secret_figure not in repair  # the submitted value is not


async def test_final_error_message_carries_no_values() -> None:
    secret_figure = "418000000"
    bad = json.dumps({"dimension": "traction", "value": secret_figure})
    client, _ = _client([_Message(bad), _Message(bad)])

    with pytest.raises(AiInvalidOutputError) as raised:
        await _run(client)

    assert secret_figure not in str(raised.value)


async def test_validation_failure_log_carries_no_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_figure = "418000000"
    bad = json.dumps({"dimension": "traction", "value": secret_figure})
    client, _ = _client([_Message(bad), _Message(_valid_score())])

    with caplog.at_level("WARNING"):
        await _run(client)

    assert secret_figure not in caplog.text


# ---------------------------------------------------------------------------
# Evidence gating (CLAUDE.md section 5)
# ---------------------------------------------------------------------------


async def test_conclusion_without_citations_is_rejected() -> None:
    """ "The model said so" is not evidence."""
    uncited = json.dumps(
        {
            "dimension": "traction",
            "value": 80,
            "sufficiency": "sufficient",
            "citations": [],
        }
    )
    client, fake = _client([_Message(uncited), _Message(uncited)])

    with pytest.raises(AiInvalidOutputError):
        await _run(client)

    assert len(fake.messages.calls) == 2


async def test_insufficient_data_may_cite_nothing() -> None:
    """Otherwise the only ways out are a fabricated citation or a fake verdict."""
    thin = json.dumps(
        {
            "dimension": "traction",
            "value": 0,
            "sufficiency": "insufficient_data",
            "citations": [],
        }
    )
    client, _ = _client([_Message(thin)])

    result = await _run(client)

    assert result.output.sufficiency is DataSufficiency.INSUFFICIENT_DATA


def test_evidence_backed_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="extra_forbidden"):
        Score.model_validate(
            {
                "dimension": "traction",
                "value": 10,
                "sufficiency": "insufficient_data",
                "citations": [],
                "verdict": "fundable",
            }
        )


def test_citation_requires_both_source_and_quote() -> None:
    with pytest.raises(ValueError, match="quote"):
        Citation.model_validate({"source_id": "deck.pdf", "quote": ""})


# ---------------------------------------------------------------------------
# Model tiering (DECISIONS.md D16)
# ---------------------------------------------------------------------------


def test_tiers_default_to_different_models() -> None:
    client, _ = _client([])

    audit = client.profile_for(ModelTier.AUDIT)
    chat = client.profile_for(ModelTier.CHAT)

    assert audit.model == ai_client.DEFAULT_AUDIT_MODEL
    assert chat.model == ai_client.DEFAULT_CHAT_MODEL
    assert audit.model != chat.model
    assert audit.max_output_tokens > chat.max_output_tokens
    assert (audit.effort, chat.effort) == ("high", "low")


def test_configured_model_overrides_the_tier_default() -> None:
    client, _ = _client([], ai_model_audit="claude-opus-4-8")

    assert client.profile_for(ModelTier.AUDIT).model == "claude-opus-4-8"
    assert client.profile_for(ModelTier.CHAT).model == ai_client.DEFAULT_CHAT_MODEL


def test_max_output_tokens_is_a_ceiling_over_both_tiers() -> None:
    client, _ = _client([], ai_max_output_tokens=1000)

    assert client.profile_for(ModelTier.AUDIT).max_output_tokens == 1000
    assert client.profile_for(ModelTier.CHAT).max_output_tokens == 1000


def test_a_ceiling_above_the_tier_budget_does_not_raise_it() -> None:
    client, _ = _client([], ai_max_output_tokens=999_999)

    audit = client.profile_for(ModelTier.AUDIT)
    assert audit.max_output_tokens < 999_999


async def test_audit_and_chat_route_to_their_own_model() -> None:
    client, fake = _client([_Message(json.dumps({"answer": "yes"}))])

    await client.complete(
        tier=ModelTier.CHAT,
        prompt=PROMPT,
        schema=Plain,
        system=[],
        messages=[{"role": "user", "content": "hi"}],
    )

    assert fake.messages.calls[0]["model"] == ai_client.DEFAULT_CHAT_MODEL


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------


async def test_schema_is_sent_as_output_config_not_output_format() -> None:
    """`output_format` parses inside the stream, hiding `stop_reason` from us."""
    client, fake = _client([_Message(_valid_score())])

    await _run(client)

    call = fake.messages.calls[0]
    assert "output_format" not in call
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["output_config"]["effort"] == "high"
    assert call["thinking"] == {"type": "adaptive"}


async def test_wire_schema_omits_keywords_the_api_rejects() -> None:
    """A raw `model_json_schema()` would 400 on the first bounded score."""
    client, fake = _client([_Message(_valid_score())])

    await _run(client)

    schema = fake.messages.calls[0]["output_config"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert "minimum" not in schema["properties"]["value"]
    assert "maximum" not in schema["properties"]["value"]
    # Demoted to prose so the model still sees the constraint.
    assert "0-100" in schema["properties"]["value"]["description"]


def test_bounds_dropped_from_the_wire_schema_are_still_enforced_on_the_response() -> (
    None
):
    """Which is what makes the mismatch-retry path fire on them."""
    with pytest.raises(ValueError, match="less_than_equal"):
        Score.model_validate(
            {
                "dimension": "traction",
                "value": 101,
                "sufficiency": "insufficient_data",
                "citations": [],
            }
        )
