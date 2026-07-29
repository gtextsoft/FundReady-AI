"""Prompt-injection defence, output validation, and tier-scoped retrieval.

Uploaded documents and chat messages are treated as **untrusted data, never as
instructions**. Nothing in them may override a system prompt, set a verdict
directly, or cause a retrieval beyond the caller's tier (CLAUDE.md section 5,
AUTH.md section 14).

Tier-scoped retrieval is the enforcement point for investor AI chat: the
retrieval layer only ever returns summary-tier data, so a prompt cannot talk its
way above the caller's tier (DECISIONS.md D8).

Implemented in TASKS.md T2.1 / T4.4.
"""
