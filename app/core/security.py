"""Token verification, current-user resolution, and RBAC dependencies.

Per AUTH.md section 3, every request: verifies the Supabase JWT signature,
`exp`, and `aud`; extracts `sub`; loads role and account status **from our
`users` table** (the source of truth -- a client-supplied role is never
trusted); and rejects a token issued before `session_valid_after`.

Provides `require_role(*roles)`, `require_kyc_verified`,
`require_active_subscription`, and the ownership helpers that prevent IDOR
(AUTH.md sections 5-6, 17).

Implemented in TASKS.md T0.4.
"""
