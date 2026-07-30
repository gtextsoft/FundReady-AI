"""Prompt-caching helpers.

Keeps token cost down by caching the stable prefix of long prompts (rubrics,
system instructions, benchmark context) across calls (DECISIONS.md D16).

**The ordering invariant.** Caching is a prefix match: the cache key is the
exact bytes up to the breakpoint, so a single byte that changes per request
invalidates everything after it. The request is rendered `tools` -> `system` ->
`messages`, which fixes the layout every call in this codebase must follow:

    1. standing rules + rubric text  (identical across calls)   <- cached
    2. prompt/rubric version marker  (changes only on release)  <- cached
    -- cache_control breakpoint --
    3. this startup's profile, this founder's question          <- not cached
    4. untrusted document + chat content, fenced (`ai.guards`)  <- not cached, last

Steps 3 and 4 are per-request and belong in `messages`, after the breakpoint.
Putting untrusted content ahead of it is wrong twice over: it destroys the hit
rate, and it puts user-submitted text above the standing rules that are meant
to govern it.

**Do not interpolate anything volatile into the cached prefix.** A timestamp, a
`startup_id`, a request id, or a per-user greeting in step 1 gives every call
its own prefix and the cache never reads. If a value changes per request, it
belongs after the breakpoint.

**Short prefixes silently will not cache.** The minimum cacheable prefix is
model-dependent -- roughly 512 tokens on the audit model and 1024 on the chat
model. Below that the API accepts `cache_control` and simply does not cache:
no error, `cache_creation_input_tokens` just stays at zero. A chat prompt
showing no hits is usually this rather than a bug. Verify with the usage
figures recorded by `ai.client`, never by assuming.

Implemented in TASKS.md T2.1.
"""

from collections.abc import Sequence

from anthropic.types import TextBlockParam


def cached_system(*sections: str) -> list[TextBlockParam]:
    """Build a system prompt whose whole prefix is cached.

    Sections are emitted in the order given and the breakpoint goes on the last
    one, so tools (rendered before `system`) and every section here are covered
    by a single cache entry.

    Every section must be stable across calls -- see the module docstring. Empty
    and whitespace-only sections are dropped so an unset optional section cannot
    change the byte layout depending on whether it was supplied.
    """
    texts = [section.strip() for section in sections if section.strip()]
    if not texts:
        return []

    blocks: list[TextBlockParam] = [
        {"type": "text", "text": text} for text in texts[:-1]
    ]
    blocks.append(
        {
            "type": "text",
            "text": texts[-1],
            "cache_control": {"type": "ephemeral"},
        }
    )
    return blocks


def uncached_system(*sections: str) -> list[TextBlockParam]:
    """Build system sections with no breakpoint, for prompts too short to cache."""
    return [
        {"type": "text", "text": section.strip()}
        for section in sections
        if section.strip()
    ]


def join_untrusted(fenced: Sequence[str]) -> str:
    """Join fenced untrusted spans into one message body.

    Always placed last in the message list, after every trusted instruction --
    the step 4 slot in the module docstring.
    """
    return "\n\n".join(span for span in fenced if span.strip())
