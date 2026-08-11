"""Claude API wrapper with model tiering.

Every model call in the platform goes through here (ARCHITECTURE.md section 6).

Cost control (DECISIONS.md D16): a cheaper model for chat and a strong model for
audits, prompt caching, a token cap per request, and a per-user daily AI budget.
Per-audit cost is tracked from day one.

Reliability: structured-output responses are validated before use and retried on
invalid output; a call either returns schema-valid JSON or fails cleanly.

---

**Three outcomes, three handlers -- never one `except`.** A call that does not
produce usable output has failed in one of three ways, and they need opposite
responses:

* `stop_reason == "refusal"` -- a safety classifier declined. Retrying the same
  request produces the same refusal, so `AiRefusalError` is raised immediately.
* `stop_reason == "max_tokens"` -- the response was cut off mid-JSON. Thinking
  is on by default on the audit model and shares the `max_tokens` budget with
  the response text, so a long rubric at high effort can spend most of the
  budget reasoning and truncate the answer. An identical retry truncates
  identically and bills twice, so `AiTruncatedError` is raised and the caller
  decides whether to re-run with more headroom.
* schema mismatch on a complete response -- the one case a retry can fix. One
  retry is made, with the failing field paths fed back in a *user* turn.

**Why the schema is passed as `output_config`, not `output_format`.** The SDK's
`output_format=Model` path parses the response inside stream accumulation, at
`content_block_stop`. A truncated or non-conforming body therefore raises
`pydantic.ValidationError` *before* `stop_reason` can be read -- which collapses
the three cases above into one indistinguishable failure. Passing the wire
schema through `output_config` disables SDK-side parsing (`parsed_output` stays
`None`), leaving `stop_reason` observable and validation ours to time.

The schema still goes through the SDK's `transform_schema`, because the API
rejects several JSON-Schema keywords that pydantic emits freely -- `minimum`,
`maximum`, `minLength`. `transform_schema` demotes them to prose in the field
description and forces `additionalProperties: false`. A raw
`model_json_schema()` would 400 the first time a model declares a bounded score.
Those bounds are then enforced by our own `model_validate_json`, which is what
makes the mismatch-retry path fire on them.

**Retries never prefill.** A last-assistant-turn prefill is a 400 on the audit
model, so the repair turn is a `user` message. It reports field paths and error
types only, never values -- model output can contain financial figures and PII,
and `core.errors` already establishes that submitted values are not echoed.

**Budgets are measured and enforced here (T5.5).** Every call returns an
`AiCallRecord` carrying per-user attribution, a timestamp, and the full token
split. `input_tokens` alone understates cost once caching works -- it counts
only the uncached remainder -- so the cache figures are recorded beside it.
Spend is checked before a call and recorded after, including on failures.

Implemented in TASKS.md T2.1.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from functools import lru_cache
from typing import Any, Final, Generic, TypeVar, cast

from anthropic import AsyncAnthropic, transform_schema
from anthropic.types import MessageParam, TextBlockParam
from pydantic import ValidationError

from app.ai.prompts import PromptVersion
from app.ai.schemas import StructuredOutput
from app.core.ai_budget import assert_within_budget, record_usage
from app.core.config import Settings

logger = logging.getLogger(__name__)

SchemaT = TypeVar("SchemaT", bound=StructuredOutput)


# ---------------------------------------------------------------------------
# Model tiering (DECISIONS.md D16)
# ---------------------------------------------------------------------------
#
# The model ids live here rather than as defaults in `core.config`, which
# deliberately ships them blank so a model choice is not smuggled in as
# configuration. T2.1 owns the choice; config overrides it per environment.
#
# Server-side fallbacks: a cyber-category refusal is a real possibility when
# auditing a cybersecurity startup. The SDK shape is
# `client.beta.messages.stream(..., fallbacks="default",
# betas=["server-side-fallback-2026-07-01"])`. Wired behind
# `Settings.ai_server_side_fallbacks_enabled` (default off) so the stable
# `messages.stream` path — and the fake clients tests inject — stay untouched
# until an environment opts in.

DEFAULT_AUDIT_MODEL: Final = "claude-opus-5"
DEFAULT_CHAT_MODEL: Final = "claude-sonnet-5"
_SERVER_SIDE_FALLBACK_BETA: Final = "server-side-fallback-2026-07-01"

# Per-tier output ceilings. `AI_MAX_OUTPUT_TOKENS`, when set, caps both: one
# global number cannot serve both tiers, so it is a ceiling rather than a value.
_AUDIT_MAX_OUTPUT_TOKENS: Final = 16_000
_CHAT_MAX_OUTPUT_TOKENS: Final = 4_096

_MAX_ATTEMPTS: Final = 2  # one call, one repair retry


class ModelTier(StrEnum):
    """Which model a call is routed to."""

    AUDIT = "audit"
    """Scoring, evidence assessment, synthesis. Strongest model, high effort."""

    CHAT = "chat"
    """Founder and investor chat. Cheaper model, low effort, latency-sensitive."""


@dataclass(frozen=True, slots=True)
class TierProfile:
    """Resolved per-tier call settings."""

    model: str
    max_output_tokens: int
    effort: str


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AiError(RuntimeError):
    """Base for every failure raised by this module.

    `usage` is what the call cost before it failed, or `None` when the failure
    happened before any request went out. Attaching it is not bookkeeping
    politeness: every one of these failures was *billed*, and the three most
    expensive calls the platform can make are all failures -- a truncated audit
    runs to the full 16k cap at high effort, and a mismatch retry bills twice.
    A budget (T5.5) that only counts successes under-counts exactly the spend
    it exists to cap.
    """

    def __init__(self, message: str, *, usage: "AiUsage | None" = None) -> None:
        super().__init__(message)
        self.usage = usage


class AiNotConfiguredError(AiError):
    """No Anthropic API key is configured. Raised before anything is billed."""


class AiRefusalError(AiError):
    """A safety classifier declined the request. Not retryable as-is."""


class AiTruncatedError(AiError):
    """The response hit `max_tokens` mid-answer. Retry needs more headroom."""


class AiInvalidOutputError(AiError):
    """The model did not return output matching the schema, after a retry."""


# ---------------------------------------------------------------------------
# Call records
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AiUsage:
    """Token usage for one call.

    `input_tokens` is the *uncached remainder* only -- total prompt size is the
    sum of all three input figures. Costing an audit from `input_tokens` alone
    silently under-reports it the moment prompt caching starts working.
    """

    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int

    @property
    def total_input_tokens(self) -> int:
        """Every input token processed, cached or not."""
        return (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )


@dataclass(frozen=True, slots=True)
class AiCallRecord:
    """What one call cost and which prompt produced it.

    Carries the attribution T5.5 needs to enforce a per-user daily budget, and
    the `prompt_ref` the pipeline persists on the AuditRun (DECISIONS.md D12).
    """

    tier: ModelTier
    model: str
    prompt_ref: str
    user_id: str | None
    occurred_at: datetime
    usage: AiUsage
    attempts: int


@dataclass(frozen=True, slots=True)
class AiResult(Generic[SchemaT]):
    """A validated model response and the record of what it cost."""

    output: SchemaT
    record: AiCallRecord


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


@lru_cache(maxsize=64)
def _wire_schema(schema: type[StructuredOutput]) -> dict[str, Any]:
    """The API-acceptable JSON Schema for a response model.

    Cached because the transform is pure and the same handful of schemas are
    used on every audit.

    **The cache is keyed on the class object and assumes the class is
    immutable.** A regenerated class is a different key and simply re-transforms;
    a class *mutated in place* keeps its key and would serve a stale schema. That
    is safe today because response models are declared statically, and it stays
    safe for T2.6 only because rubric versions are frozen rather than edited
    (DECISIONS.md D12). Build a new class per version; never rewrite one.
    """
    return transform_schema(schema)


class AiClient:
    """The only object in the codebase that talks to the Claude API.

    The underlying SDK client is injectable so tests can drive refusal,
    truncation, and mismatch paths without a network call. Construction does not
    reach the network, so a half-configured development environment still boots.
    """

    def __init__(
        self, settings: Settings, client: AsyncAnthropic | None = None
    ) -> None:
        self._settings = settings
        self._client = client if client is not None else _build_client(settings)

    def profile_for(self, tier: ModelTier) -> TierProfile:
        """Resolve the model, output cap, and effort for a tier."""
        settings = self._settings
        if tier is ModelTier.AUDIT:
            model = settings.ai_model_audit.strip() or DEFAULT_AUDIT_MODEL
            max_tokens = _AUDIT_MAX_OUTPUT_TOKENS
            # Analytical work, not latency-sensitive, and wrong answers are
            # expensive downstream -- a founder acts on this report.
            effort = "high"
        else:
            model = settings.ai_model_chat.strip() or DEFAULT_CHAT_MODEL
            max_tokens = _CHAT_MAX_OUTPUT_TOKENS
            # Someone is waiting on the reply, and retrieval has already
            # narrowed what there is to reason about.
            effort = "low"

        ceiling = settings.ai_max_output_tokens
        if ceiling is not None and ceiling > 0:
            max_tokens = min(max_tokens, ceiling)

        return TierProfile(model=model, max_output_tokens=max_tokens, effort=effort)

    async def complete(
        self,
        *,
        tier: ModelTier,
        prompt: PromptVersion,
        schema: type[SchemaT],
        system: list[TextBlockParam],
        messages: list[MessageParam],
        user_id: str | None = None,
    ) -> AiResult[SchemaT]:
        """Run one structured call and return validated output, or raise.

        `system` should come from `ai.caching` and `messages` should end with
        the fenced untrusted content from `ai.guards` -- the ordering invariant
        is documented in `ai.caching`, and this method does not reorder what it
        is given.
        """
        profile = self.profile_for(tier)
        attempt_messages = list(messages)
        usage = AiUsage(0, 0, 0, 0)
        assert_within_budget(user_id, settings=self._settings)

        try:
            for attempt in range(1, _MAX_ATTEMPTS + 1):
                try:
                    text, call_usage = await self._call(
                        profile=profile,
                        schema=schema,
                        system=system,
                        messages=attempt_messages,
                    )
                except AiError as error:
                    # `_call` only knows what its own request cost. Fold in what
                    # earlier attempts already spent, or a refusal on the retry
                    # would report half the bill.
                    error.usage = _accumulate(
                        usage, error.usage or AiUsage(0, 0, 0, 0)
                    )
                    raise
                usage = _accumulate(usage, call_usage)

                try:
                    output = schema.model_validate_json(text)
                except ValidationError as error:
                    problems = _describe_without_values(error)
                    logger.warning(
                        "ai output failed validation",
                        extra={
                            "context": {
                                "tier": tier.value,
                                "model": profile.model,
                                "prompt": prompt.ref,
                                "attempt": attempt,
                                "problems": problems,
                            }
                        },
                    )
                    if attempt == _MAX_ATTEMPTS:
                        raise AiInvalidOutputError(
                            f"{prompt.ref} returned output that does not match "
                            f"{schema.__name__} after {attempt} attempts: "
                            f"{problems}",
                            usage=usage,
                        ) from None
                    attempt_messages = [*attempt_messages, _repair_turn(problems)]
                    continue

                return AiResult(
                    output=output,
                    record=AiCallRecord(
                        tier=tier,
                        model=profile.model,
                        prompt_ref=prompt.ref,
                        user_id=user_id,
                        occurred_at=datetime.now(UTC),
                        usage=usage,
                        attempts=attempt,
                    ),
                )

            raise AssertionError("unreachable: the loop returns or raises")
        finally:
            billed = usage.total_input_tokens + usage.output_tokens
            if billed > 0:
                record_usage(user_id, billed, settings=self._settings)

    async def _call(
        self,
        *,
        profile: TierProfile,
        schema: type[SchemaT],
        system: list[TextBlockParam],
        messages: list[MessageParam],
    ) -> tuple[str, AiUsage]:
        """One request. Returns the response text, or raises on a hard failure."""
        output_config = cast(
            Any,
            {
                "format": {"type": "json_schema", "schema": _wire_schema(schema)},
                "effort": profile.effort,
            },
        )

        # Streamed even though nothing consumes the increments: a non-streaming
        # request with a large `max_tokens` risks an HTTP timeout, and the audit
        # tier runs near the top of its budget by design.
        stream_kwargs: dict[str, Any] = {
            "model": profile.model,
            "max_tokens": profile.max_output_tokens,
            "system": system,
            "messages": messages,
            "output_config": output_config,
            "thinking": {"type": "adaptive"},
        }
        if self._settings.ai_server_side_fallbacks_enabled:
            # Beta namespace only — keeps the default path on `messages.stream`
            # so injected test doubles that lack `.beta` continue to work.
            async with self._client.beta.messages.stream(
                **stream_kwargs,
                fallbacks="default",
                betas=[_SERVER_SIDE_FALLBACK_BETA],
            ) as stream:
                message = await stream.get_final_message()
        else:
            async with self._client.messages.stream(**stream_kwargs) as stream:
                message = await stream.get_final_message()

        usage = AiUsage(
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            cache_creation_input_tokens=message.usage.cache_creation_input_tokens or 0,
            cache_read_input_tokens=message.usage.cache_read_input_tokens or 0,
        )

        # Checked before the content is touched. A refusal carries no text block
        # at all, and a truncated response carries a partial one that would fail
        # validation for a reason that has nothing to do with the schema.
        if message.stop_reason == "refusal":
            raise AiRefusalError(
                f"{profile.model} declined the request "
                f"(stop_reason=refusal); not retryable with the same input",
                usage=usage,
            )
        if message.stop_reason == "max_tokens":
            raise AiTruncatedError(
                f"{profile.model} hit the {profile.max_output_tokens}-token output "
                "cap before completing; re-run with more headroom or lower effort",
                usage=usage,
            )

        # A blank text block counts as no text block. Both are "the model
        # returned nothing", and neither is retried: the repair turn works by
        # naming which fields were wrong, and an empty body gives it nothing to
        # name. Retrying would spend a second call to re-ask the same question.
        text = next(
            (
                block.text
                for block in message.content
                if block.type == "text" and block.text.strip()
            ),
            None,
        )
        if text is None:
            raise AiInvalidOutputError(
                f"{profile.model} returned no usable text block "
                f"(stop_reason={message.stop_reason})",
                usage=usage,
            )
        return text, usage


def _build_client(settings: Settings) -> AsyncAnthropic:
    """Build the SDK client, or explain which setting is missing."""
    key = settings.anthropic_api_key
    if key is None or not key.get_secret_value().strip():
        raise AiNotConfiguredError("ANTHROPIC_API_KEY is not set")
    return AsyncAnthropic(api_key=key.get_secret_value())


def _accumulate(total: AiUsage, call: AiUsage) -> AiUsage:
    """Sum usage across attempts, so a retry's cost is not lost."""
    return AiUsage(
        input_tokens=total.input_tokens + call.input_tokens,
        output_tokens=total.output_tokens + call.output_tokens,
        cache_creation_input_tokens=(
            total.cache_creation_input_tokens + call.cache_creation_input_tokens
        ),
        cache_read_input_tokens=(
            total.cache_read_input_tokens + call.cache_read_input_tokens
        ),
    )


def _describe_without_values(error: ValidationError) -> str:
    """Summarise a validation failure as field paths and error types.

    Never includes the offending value. Model output can carry financial
    figures and PII, and this string reaches both a log line and an exception
    message (CLAUDE.md section 4).
    """
    problems = sorted(
        {
            f"{'.'.join(str(part) for part in item['loc']) or '<root>'} "
            f"({item['type']})"
            for item in error.errors()
        }
    )
    return ", ".join(problems)


def _repair_turn(problems: str) -> MessageParam:
    """The retry turn naming what failed.

    A `user` turn, not an assistant prefill -- prefilling the last assistant
    message is a 400 on the audit model.
    """
    return {
        "role": "user",
        "content": (
            "Your previous response did not match the required JSON schema.\n"
            f"Problems: {problems}.\n"
            "Return the complete JSON object again, conforming exactly to the "
            "schema. Do not add commentary before or after it."
        ),
    }
