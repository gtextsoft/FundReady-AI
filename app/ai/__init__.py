"""Shared AI orchestration.

The **only** place in the codebase that talks to the Claude API. Feature modules
reach it through their `service` layer -- never directly from a router
(ARCHITECTURE.md sections 3, 6).

Standing rules (CLAUDE.md section 5):
- The model interprets; it never produces financial figures (DECISIONS.md D9).
- Every call returns JSON validated against a schema; raw model text is never
  passed to a client.
- Uploaded documents and user chat are **untrusted input**. They can never
  override system instructions, change a verdict directly, or widen data access.
- Investor chat retrieval is summary-tier only, enforced in the retrieval layer
  rather than in the prompt.
- Prompts and rubrics are versioned and recorded on every AuditRun.
"""
