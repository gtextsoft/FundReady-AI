"""Password hashing, token issue/verification, and the authorization deps.

Authentication is **ours** (DECISIONS.md D4) -- no managed identity provider
absorbs a mistake here on our behalf. `AUTH.md` is the spec; the essentials:

* **Passwords** are hashed with Argon2id at the configured cost, rehashed on
  login when that cost rises, and verified in constant time. An unknown email
  still performs a dummy hash so response timing does not reveal whether an
  account exists.
* **Access tokens** are short-lived JWTs we sign. Verification checks the
  signature, `exp`, `iat`, `iss`, `aud`, and `typ` -- and the algorithm is
  **pinned from settings, never read from the token header** (that is how
  `alg: none` and algorithm-confusion attacks get in).
* **Refresh tokens** are opaque random strings stored hashed, rotating on every
  use. Presenting a used one means theft: revoke the whole family, bump
  `session_valid_after`, and audit-log it.
* **Role and account status come from the database on every request**, never
  from a token claim. That is what makes revocation, suspension, and role
  changes take effect immediately.

Provides `require_role(*roles)`, `require_kyc_verified`,
`require_active_subscription`, and the ownership helpers that prevent IDOR --
which, with self-built auth, are the *primary* tenant-isolation wall
(DECISIONS.md D13), not a convenience on top of RLS.

Implemented in TASKS.md T0.4 / T1.2.
"""
