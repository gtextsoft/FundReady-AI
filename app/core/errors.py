"""Typed exceptions, the error envelope, and the global exception handlers.

Every error response uses the one documented envelope (CLAUDE.md section 6):

    {"error": {"code": "...", "message": "...", "details": {...}}}

Error codes are stable and documented. Stack traces, secrets, and PII never
reach a response body or a log line.

Implemented in TASKS.md T0.3.
"""
