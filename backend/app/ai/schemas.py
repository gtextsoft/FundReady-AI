"""Structured-output JSON schemas for model responses.

Audits, dimension scores, and evidence assessments are validated against these
before anything downstream sees them. Invalid output is rejected and retried;
raw model text never reaches a client (CLAUDE.md section 5).

Implemented in TASKS.md T2.1.
"""
