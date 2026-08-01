"""T2.1 done-condition, against the real API.

Skipped without `ANTHROPIC_API_KEY`. These tests exist because the unit suite
cannot prove the one thing that matters most here: that the request shape
`ai.client` builds is a shape the API *accepts*. A fake transport happily
returns whatever it was scripted with, so a schema the API would reject with a
400, a beta parameter that does not exist, or an unsupported model id all pass
mocked and fail in production.

Deliberately cheap: the chat tier, a small schema, a trivial prompt. This is a
contract check, not an audit.
"""

import pytest

from app.ai import caching, guards
from app.ai.client import AiClient, ModelTier
from app.ai.prompts import PromptVersion
from app.ai.schemas import StructuredOutput
from app.core.config import Settings
from tests.conftest import ANTHROPIC_API_KEY, requires_anthropic_key

# `billed` is deselected by default (see pyproject). Run with `pytest -m billed`.
# The skipif is not enough on its own: it protects an unconfigured machine, not
# a configured one, so without the marker adding the CI secret would start
# spending on every push.
pytestmark = [pytest.mark.integration, pytest.mark.billed, requires_anthropic_key]

PROMPT = PromptVersion(
    name="live_smoke",
    version=1,
    text="You extract structured facts. Answer only from the data given.",
)


class Colour(StructuredOutput):
    """Small enough that a failure is the request shape, not the task."""

    name: str
    hex_code: str


def _client() -> AiClient:
    assert ANTHROPIC_API_KEY is not None
    return AiClient(Settings(anthropic_api_key=ANTHROPIC_API_KEY))


async def test_a_live_call_returns_schema_valid_json() -> None:
    result = await _client().complete(
        tier=ModelTier.CHAT,
        prompt=PROMPT,
        schema=Colour,
        system=caching.uncached_system(PROMPT.text),
        messages=[
            {
                "role": "user",
                "content": "The colour crimson, hex #DC143C. Return it.",
            }
        ],
        user_id="live-smoke",
    )

    assert result.output.name
    assert result.output.hex_code
    assert result.record.attempts == 1
    assert result.record.usage.output_tokens > 0
    assert result.record.prompt_ref == "live_smoke@1"


async def test_the_wire_schema_is_accepted_for_a_bounded_evidence_schema() -> None:
    """The 400 this guards against: `minimum` reaching the API in a schema.

    Uses the real `EvidenceBacked` shape -- nested `$defs`, a StrEnum, a bounded
    integer -- because that combination is what every rubric output in T2.6 will
    be built from.
    """
    from tests.unit.test_ai_client import Score

    result = await _client().complete(
        tier=ModelTier.CHAT,
        prompt=PROMPT,
        schema=Score,
        system=caching.uncached_system(PROMPT.text, guards.UNTRUSTED_RULE),
        messages=[
            {
                "role": "user",
                "content": (
                    "Score the 'traction' dimension from this data.\n"
                    + guards.fence(
                        "Monthly recurring revenue grew from 2.0m to 4.1m NGN "
                        "over six months across 34 paying customers.",
                        label="metrics.txt",
                    ).text
                ),
            }
        ],
        user_id="live-smoke",
    )

    assert 0 <= result.output.value <= 100
    assert result.output.citations, "a conclusion must cite the submitted data"


async def test_prompt_caching_reports_usage_figures() -> None:
    """That the usage figures parse and are real -- NOT that caching happened.

    The prefix here is one sentence, far below the 1024-token minimum on the
    chat model, so both cache counters are necessarily zero. Asserting that
    explicitly is the point: it is falsifiable, unlike `>= 0`, and it fails
    loudly if the minimum drops or this prompt grows past it -- at which point
    the premise of this test has changed and it should be rewritten to assert a
    real hit (DECISIONS.md D16).
    """
    result = await _client().complete(
        tier=ModelTier.CHAT,
        prompt=PROMPT,
        schema=Colour,
        system=caching.cached_system(PROMPT.text),
        messages=[{"role": "user", "content": "The colour teal, hex #008080."}],
    )

    usage = result.record.usage
    # Can fail: proves the SDK populated the fields rather than defaulting them.
    assert usage.input_tokens > 0, "prompt tokens were billed but not reported"
    assert usage.output_tokens > 0, "a response arrived but reported no tokens"
    assert usage.cache_creation_input_tokens == 0, (
        "the prefix is below the cacheable minimum, so nothing should be written"
    )
    assert usage.cache_read_input_tokens == 0, (
        "the prefix is below the cacheable minimum, so nothing should be read"
    )
    assert usage.total_input_tokens == usage.input_tokens
