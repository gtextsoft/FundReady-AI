"""Idempotent background job handlers.

Handlers (`run_audit`, `assess_evidence`, ...) must be safe to retry: a repeated
run must not duplicate an AuditRun, re-charge a founder, or double-spend AI
budget (DECISIONS.md D14).

Implemented in TASKS.md T2.8 / T3.5.
"""
