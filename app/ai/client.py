"""Claude API wrapper with model tiering.

Every model call in the platform goes through here (ARCHITECTURE.md section 6).

Cost control (DECISIONS.md D16): a cheaper model for chat and a strong model for
audits, prompt caching, a token cap per request, and a per-user daily AI budget.
Per-audit cost is tracked from day one.

Reliability: structured-output responses are validated before use and retried on
invalid output; a call either returns schema-valid JSON or fails cleanly.

Implemented in TASKS.md T2.1.
"""
