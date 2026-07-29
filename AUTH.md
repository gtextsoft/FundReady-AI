# AUTH.md — Authentication & Authorization

Security spec for identity and access in the FundReady backend. This is the backbone of the tier and isolation model in `DECISIONS.md` (D8, D13) and `CLAUDE.md` §4. Nothing here is optional.

> **Revised 2026-07-29** for the D4 stack change. Authentication is now **built in FastAPI** — we own password hashing, token issuance, refresh rotation, MFA, and revocation. There is no managed identity provider and no `auth.uid()`. The previous revision assumed Supabase Auth; every mechanism below replaces it.

---

## 1. Principles

- **Authenticate at the edge, authorize at every layer.** A valid token proves *who*; it never proves *allowed*.
- **Never trust the client** for identity, role, tier, ownership, or payment/KYC state. All of it is derived server-side.
- **We are the identity provider now.** No provider absorbs a mistake here on our behalf. Password storage, token lifetime, rotation, lockout, and revocation are all our responsibility, and each is specified below rather than left to judgement.
- **Ownership checks are the primary isolation wall** (D13). Postgres RLS is an optional backstop, not the first line.
- **Least privilege.** Every actor gets the minimum. Admin power is the exception, not the default.
- **Role ≠ permission.** Access = role **and** conditions (KYC, subscription, account status) **and** ownership **and** tier.

## 2. The three roles

| Role | Who | Can (subject to the gates in §5–§8) |
|---|---|---|
| **Founder** | Business owner being audited | Manage **their own** startup profile & documents; view **their own** audit + tasks; buy products; subscribe; upload evidence; browse events |
| **Investor** | Capital provider | After KYC: discover investor-ready startups; view **summaries**; chat with the AI analyst (summary-tier only); express interest; book meetings; browse events |
| **SACI Admin** | SACI Holdings (the broker) | Everything: full reports, approve matches, schedule meetings, **reveal full reports**, manage products/events, manage users. Every admin action is audit-logged |

Role is coarse. The real access decision layers conditions on top (§5).

## 3. Authentication

**We issue and verify our own credentials.** Passwords are hashed with Argon2id; sessions are a short-lived JWT access token plus a long-lived, rotating, server-side refresh token.

### 3.1 Password storage

- **Argon2id** via `argon2-cffi`. Never MD5/SHA/bcrypt-only, never a homegrown scheme.
- Parameters are **configurable per environment** so they can be raised without a code change, with these defaults:

  | Parameter | Default | Floor (never go below) |
  |---|---|---|
  | memory cost | 65536 KiB (64 MiB) | 19456 KiB (19 MiB) |
  | time cost | 3 | 2 |
  | parallelism | 1 | 1 |
  | hash length | 32 bytes | 32 bytes |
  | salt length | 16 bytes (random per password) | 16 bytes |

  The floor is OWASP's minimum. **Mind the memory arithmetic on a small host:** 64 MiB × concurrent logins is real RAM, so on a 512 MB instance either cap login concurrency or drop to the floor. This is a deployment decision, not a code one — hence the env vars.
- The hash string embeds its own parameters, so **rehash on login** when the stored parameters are below current settings. Verify with the old cost, then transparently upgrade.
- **Verification is constant-time** (the library's `verify`). A failed lookup still performs a dummy hash so response timing does not reveal whether an email exists.
- The plaintext password exists only inside the request that carried it. It is never logged, never stored, never included in an error, and never returned.

### 3.2 Registration

- **Founder / Investor:** self-service. `POST /v1/auth/register` creates the user with `status = pending_verification` and sends a verification email.
- **Email verification is required before any sensitive action** — buying, uploading, discovery, interest. Browsing one's own empty account is permitted while unverified.
- **Admin: no self-service.** Admins are provisioned only by an existing admin, and that creation is itself audit-logged (§9).
- Registration responses are **identical whether or not the email already exists** — otherwise the endpoint is an account-enumeration oracle. The differing behaviour is in the email that gets sent, not the API response.

### 3.3 Login

`POST /v1/auth/login` with email + password:

1. Look up the user by normalised (lower-cased, trimmed) email.
2. Verify the password with Argon2id — including the dummy-hash path when the user does not exist.
3. Reject if `status = suspended`, or if the account is inside a lockout window (§12).
4. If MFA is enabled, do **not** issue tokens yet — return an MFA challenge (§9.1).
5. Issue an access token + refresh token (§4), record `last_login_at`, reset the failed-login counter.
6. On failure: increment the failed-login counter, apply backoff/lockout, and return the **same generic error** regardless of cause.

### 3.4 Verifying a request

Every protected request:

1. Read `Authorization: Bearer <access_token>`.
2. **Verify the signature** against our signing key, and verify `exp`, `iat`, `iss`, `aud`, and `typ = "access"`. Reject `alg: none` and reject any algorithm other than the configured one — the algorithm is pinned in code, never taken from the token header.
3. Extract the user id from `sub`.
4. **Load the user's role and account status from the `users` table** — the source of truth. A `role` claim may ride in the token for convenience, but **authorization always reads the database.** One indexed primary-key lookup per request is the price of immediate revocation, suspension, and role change; it is worth paying.
5. Reject if `status != active` or if `iat < session_valid_after` (§11).

## 4. Tokens

### 4.1 Access token (JWT)

- **Lifetime 15 minutes.** Short, because it is not individually revocable — revocation works through `session_valid_after` (§11).
- **Signing algorithm: HS256** with a strong secret from the environment. One service both issues and verifies, so an asymmetric keypair buys nothing today. The header carries a `kid` so the key can be rotated (verify against current + previous, sign with current), and the algorithm is a single config value — moving to EdDSA later is a configuration change, not a redesign.
- **Claims:**

  | Claim | Meaning |
  |---|---|
  | `sub` | user id (uuid) |
  | `typ` | `"access"` — a refresh token must never be accepted as an access token |
  | `iat` / `exp` | issued-at / expiry, both checked |
  | `iss` / `aud` | issuer and audience, both checked |
  | `jti` | unique token id, for correlation |
  | `role` | **convenience only.** Never the basis of an authorization decision |

- Sent as `Authorization: Bearer` over HTTPS only. **Never** in a URL, query string, log line, or error message.

### 4.2 Refresh token

- **Opaque, high-entropy random string** (≥32 bytes from `secrets.token_urlsafe`) — not a JWT. It is a database-backed handle, so it is revocable in a way a JWT is not.
- **Stored hashed** (SHA-256) in `refresh_tokens`. A database leak must not yield usable sessions. The plaintext is returned to the client exactly once, at issue.
- **Lifetime 30 days**, sliding through rotation.
- **Rotating:** every `POST /v1/auth/refresh` invalidates the presented token and issues a new one. The old row is marked `used_at` and linked to its replacement.
- **Reuse detection:** presenting an already-used refresh token means the token was stolen (either the thief or the legitimate client is replaying). Response: **revoke the entire token family**, bump `session_valid_after`, write an audit-log entry, and force re-authentication. This is the single most valuable control in the whole token design — a stolen refresh token buys the attacker one use before the session dies.
- **Family:** every token descended from one login shares a `family_id`, which is what reuse detection revokes.
- Stored by the mobile app in secure device storage (iOS Keychain / Android Keystore) — never plain storage.

### 4.3 Transport and status codes

- TLS everywhere. Reject non-HTTPS.
- **`401` vs `403` (contract for mobile):** `401` = missing/invalid/expired token → the client refreshes once and retries. `403` = authenticated but not permitted (role / condition / ownership / tier) → do not retry; surface the appropriate state.

## 5. Authorization model (layered)

Every protected endpoint passes through these in order; failing any is a denial:

1. **Authenticated** — valid token (§3.4).
2. **Account status** — `active` (not `suspended` / `pending_verification`).
3. **Role** — RBAC: the endpoint's allowed role(s).
4. **Condition/entitlement** — e.g. investor `kyc_status = verified`; founder `subscription_status = active`.
5. **Ownership** — object-level: the actor owns, or is party to, the resource (§6).
6. **Tier serialization** — the response returns only fields the actor's tier allows (§7).

### Permission matrix (✓ allowed · ⚙ conditional · ✗ denied)

| Action | Founder | Investor | Admin |
|---|---|---|---|
| Create/edit **own** startup | ✓ | ✗ | ✓ |
| View **own** audit + tasks | ✓ | ✗ | ✓ |
| Buy product / subscribe | ✓ | ✗ | ✓ |
| Upload evidence (own task) | ✓ | ✗ | ✓ |
| Browse events catalogue | ✓ | ✓ | ✓ |
| Discover startups | ✗ | ⚙ KYC verified | ✓ |
| View startup **summary** | ✗ | ⚙ KYC verified | ✓ |
| Investor AI chat (summary-tier) | ✗ | ⚙ KYC verified | ✓ |
| Express interest / book meeting | ✗ | ⚙ | ✓ |
| Approve match | ✗ | ✗ | ✓ |
| **Reveal full report** | ✗ | ✗ | ✓ (logged) |
| View **any** startup's full report | ✗ | ✗ | ✓ |
| Manage products/events | ✗ | ✗ | ✓ |
| Manage users / roles | ✗ | ✗ | ✓ (logged) |

## 6. Object-level authorization (IDOR prevention) — the primary isolation wall

Per `DECISIONS.md` **D13**, this is where tenant isolation is actually enforced. RLS (§10) is a backstop behind it, not a substitute.

- Ownership is checked on **every** access to a specific object — never inferred from the URL, and never from an id the client supplied as "theirs".
- A founder can only read/write rows where `owner_id = current_user.id`. Passing another founder's `startup_id` returns **`404`, not `403`** — a 403 would confirm the id exists.
- An investor can only act on interests and meetings they are a party to.
- Enforced in the **service layer**. A router must never perform the check itself, and must never be the only thing that does.
- **A missing ownership check is a security bug even if RLS would have caught it.**

## 7. Report-tier authorization

Per `DECISIONS.md` **D8** (SECURITY INVARIANT) — unchanged by the stack move:

- **Investor →** summary serializer only. No code path returns full-report fields to an investor.
- **Founder →** their own audit/tasks serializer only; never another startup's data; never SACI's internal notes/positioning.
- **Admin →** full.
- The **full-report reveal is an explicit admin action**, audit-logged, and is the *only* way an investor ever sees full contents (at the meeting). Tier filtering lives in the response serializers, enforced by services — never by the client.

## 8. Conditional gates

- **Investor KYC (Stripe Identity):** an investor with `kyc_status != verified` is blocked from discovery, summaries, AI chat, and interest — enforced by a `require_kyc_verified` dependency. Status is trusted from Stripe only.
- **Founder subscription (Stripe Billing):** founder access is gated by `subscription_status = active`, trusted from Stripe webhooks/API only — never from the client.
- **Account status:** `suspended` blocks everything except logout. `pending_verification` blocks every sensitive action.

## 9. Admin hardening

The admin role is the highest-value target — it can reveal any full report — so it is treated accordingly:

- **MFA required** for all admin accounts. Founders/investors: optional but supported.
- Enrolling requires being logged in, so an admin who has not yet enrolled **is** issued tokens — but `require_role(ADMIN)` refuses every admin capability until `mfa_enabled` is true. The second factor gates the *power*, not the session; there is no window in which admin actions are reachable without it.
- **No self-service admin signup**; provisioned by an existing admin; creation logged.
- **Every admin action is written to the immutable audit log** (who, what, target, when) — especially report reveals, tier changes, and user/role changes.
- Consider IP allow-listing or a separate admin surface later; v1 enforces MFA + logging.
- Single admin role in v1; sub-roles can come later.

### 9.1 MFA (ours to build)

- **TOTP, RFC 6238** (`pyotp`), 30-second step, ±1 step tolerance for clock drift, 6 digits.
- The shared secret is **encrypted at rest** with a key from the environment — not stored in plaintext, because a database leak would otherwise defeat the second factor entirely.
- Enrolment is confirmed by verifying one code before MFA is marked enabled; otherwise a user can lock themselves out.
- **Recovery codes:** 10 single-use codes, shown once, **stored hashed** (Argon2id, same as passwords) and consumed on use.
- A used TOTP code is rejected for the remainder of its step, so an intercepted code cannot be replayed.
- MFA is verified **after** the password (§3.3) and before any token is issued.

## 10. Row-Level Security (optional second wall)

Per D13, RLS is **secondary**. With self-built auth the database has no independent notion of the caller — the application is the only thing that verified the token — so RLS can only enforce what the application tells it.

Where enabled, identity is passed **per transaction** and policies read it back:

```sql
-- Set by the application at the start of each request's transaction:
SET LOCAL app.current_user_id = '<uuid>';

-- Founders read only their own startups
create policy founder_reads_own_startup on startups
for select using (owner_id = current_setting('app.current_user_id', true)::uuid);

-- Founders write only their own startups
create policy founder_writes_own_startup on startups
for all using (owner_id = current_setting('app.current_user_id', true)::uuid)
       with check (owner_id = current_setting('app.current_user_id', true)::uuid);
```

Notes that matter:

- **`SET LOCAL`, never `SET`** — the value must die with the transaction, or a pooled connection carries one user's identity into another user's request. This is the failure mode to test for.
- Trusted server code (workers, migrations) runs under a role that is exempt, and that role is never used on a request path serving an end user.
- `current_setting(..., true)` returns NULL rather than erroring when unset, so a forgotten `SET LOCAL` denies rather than crashes.

## 11. Sessions, revocation & compromise

- **Logout:** revoke the presented refresh token and its family. The access token expires within 15 minutes.
- **Logout everywhere / ban / password change / role change:** bump the user's `session_valid_after`; the backend rejects any access token with `iat < session_valid_after`, and all refresh tokens for the user are revoked. This invalidates outstanding tokens without waiting for expiry.
- **Refresh reuse** is treated as theft → revoke the whole family, bump `session_valid_after`, log it, force re-auth (§4.2).
- **Suspicion/compromise:** set `status = suspended` and bump `session_valid_after`.
- A password change **always** bumps `session_valid_after` — otherwise the old session survives the very event meant to end it.

## 12. Password & account security

- Argon2id per §3.1. Passwords are never stored or logged in plaintext by us.
- **Minimum strength:** at least 12 characters; reject the obvious (email local-part, the word "fundready", common-password list). Length beats composition rules — no forced symbol classes.
- **Breached-password check** via the HIBP range API (k-anonymity: only a 5-character SHA-1 prefix leaves our servers, never the password). Free, no key. **Fails open** — if the service is unreachable the signup proceeds and the failure is logged, because an outage at a third party must not stop registration.
- **Email verification** required before sensitive actions. Verification tokens are single-use, expiring (24 h), and **stored hashed**.
- **Password reset:** single-use, expiring (1 h), hashed-at-rest token, delivered by email. Requesting a reset returns the **same response whether or not the account exists**. Completing a reset bumps `session_valid_after` and revokes every refresh token.
- **Rate limiting and lockout** on login, registration, password-reset, refresh, and MFA verification — per-IP and per-account. Exponential backoff, then a temporary lock, to blunt credential stuffing. Backed by Redis (already in the stack); implementation lands in T5.5.

## 13. Security controls checklist

- [ ] TLS enforced; HTTP rejected.
- [ ] Argon2id hashing at or above the configured parameters; rehash-on-login when parameters rise.
- [ ] JWT signature + `exp` + `iat` + `iss` + `aud` + `typ` verified on every request; algorithm pinned in code; `none` rejected.
- [ ] Role/status loaded from the database (source of truth); a `role` claim is never the basis of a decision.
- [ ] Refresh tokens opaque, hashed at rest, rotating, with family revocation on reuse.
- [ ] `session_valid_after` bumped on password change, role change, suspension, and reuse detection.
- [ ] **Ownership checked in the service layer on every object access** (primary wall); other-tenant ids return 404.
- [ ] RLS policies, where enabled, use `SET LOCAL` — verified not to leak across pooled connections.
- [ ] Tier serializers applied to every response that carries report data.
- [ ] KYC and subscription gates enforced server-side from Stripe only.
- [ ] MFA required for admins; TOTP secrets encrypted at rest; recovery codes hashed.
- [ ] Rate limiting + lockout on all auth endpoints; uniform responses that do not enumerate accounts.
- [ ] CORS restricted to known origins; secure response headers set.
- [ ] All admin/auth-sensitive actions written to the immutable audit log.
- [ ] Secrets (JWT signing key, MFA encryption key, database URL, R2 credentials) in env/secret manager; never in code, logs, or git.

## 14. Threats & mitigations

| Threat | Mitigation |
|---|---|
| Credential stuffing / brute force | Rate limits, lockout/backoff, breached-password check, MFA |
| Offline cracking after a database leak | Argon2id with tuned parameters; refresh tokens and MFA secrets not usable as stored |
| Token theft (device/network) | 15-minute access TTL, TLS, secure device storage, refresh rotation + **reuse detection**, `session_valid_after` |
| Refresh-token replay | Family revocation on reuse — a stolen token buys one use, then kills the session |
| Algorithm-confusion / `alg: none` | Algorithm pinned server-side; token header never consulted for it |
| Access token used as refresh (or vice versa) | `typ` claim checked on both paths |
| IDOR (accessing others' data) | Service-layer ownership checks (primary) + optional RLS; ids never trusted from the client |
| Account enumeration | Uniform responses on register, login, and password-reset; dummy hash on unknown user |
| Privilege escalation | Role read from the database, not the token; admin manual-provision + MFA + logging |
| Connection-pool identity bleed | `SET LOCAL` only, scoped to the transaction; explicitly tested |
| Payment/KYC spoofing | State trusted only from Stripe webhooks/API |
| Tier leakage (investor sees full report) | Server-side tier serializers; reveal is an admin-only, logged action (D8) |
| Prompt-driven data exfiltration via AI chat | Investor chat retrieval is summary-tier only, enforced in the retrieval layer, not the prompt (`CLAUDE.md` §5) |

## 15. Auth data model

`users` — our source of truth:

- `id` (uuid, pk) · `email` (unique, normalised lower-case) · `password_hash` · `role` · `status`
- `email_verified_at` · `mfa_enabled` · `mfa_secret_encrypted`
- `kyc_status` (investors) · `subscription_status` (founders)
- `session_valid_after` (timestamptz) · `failed_login_count` · `locked_until`
- `last_login_at` · `created_at` · `updated_at`

`refresh_tokens`:

- `id` (uuid, pk) · `user_id` · `family_id` · `token_hash` (sha256)
- `issued_at` · `expires_at` · `used_at` · `revoked_at` · `replaced_by_id`
- `device_label` (optional, user-supplied and untrusted)

`auth_tokens` (email verification and password reset):

- `id` · `user_id` · `purpose` (`email_verification` | `password_reset`) · `token_hash` · `expires_at` · `used_at` · `created_at`

`mfa_recovery_codes`:

- `id` · `user_id` · `code_hash` · `used_at`

`audit_log` (immutable): `actor_id` · `action` · `target_type` · `target_id` · `metadata` · `created_at`.

Enums:
- `role`: `founder` · `investor` · `admin`
- `account_status`: `pending_verification` · `active` · `suspended`
- `kyc_status`: `none` · `pending` · `verified` · `failed`
- `subscription_status`: `none` · `active` · `past_due` · `canceled`

## 16. API surface (what the mobile developer calls)

| Endpoint | Purpose |
|---|---|
| `POST /v1/auth/register` | Create a founder or investor account |
| `POST /v1/auth/login` | Email + password → tokens, or an MFA challenge |
| `POST /v1/auth/mfa/enroll` | Issue a TOTP secret + `otpauth://` URI. Does **not** enable MFA |
| `POST /v1/auth/mfa/confirm` | Confirm with one code → enables MFA, returns 10 recovery codes (shown once) |
| `POST /v1/auth/mfa/verify` | Complete an MFA challenge with a TOTP **or** recovery code → tokens |
| `POST /v1/auth/refresh` | Rotate the refresh token → new token pair |
| `POST /v1/auth/logout` | Revoke the current refresh token family |
| `POST /v1/auth/verify-email` | Confirm an email with the emailed token |
| `POST /v1/auth/password-reset/request` | Begin a reset (uniform response) |
| `POST /v1/auth/password-reset/confirm` | Complete a reset; ends all sessions |
| `GET /v1/users/me` | The caller's own profile, role, and gate status |

Client responsibilities:

- Store access + refresh tokens in secure device storage (Keychain/Keystore).
- On `401`: refresh once and retry; if refresh fails, send the user to login.
- On `403`: do not retry — show the appropriate "not allowed / verify first" state.
- Trigger the **KYC flow** (investors) and **subscription flow** (founders) when the API signals the gate is unmet.
- Never cache or display data beyond what the API returns (the API already tier-filters).

## 17. Implementation checklist (expands TASKS.md T0.4 / T1.2 / T1.3 / T4.1)

- [ ] `core/security.py`: Argon2id hash/verify with rehash-on-login; JWT issue/verify with pinned algorithm and `typ` checking.
- [ ] JWT verification dependency: verify → load user → check status and `session_valid_after`.
- [ ] `require_role(*roles)`, `require_kyc_verified`, `require_active_subscription`, `get_current_founder/investor/admin` dependencies.
- [ ] Ownership helpers (e.g. `get_owned_startup`) returning 404 on mismatch.
- [ ] `identity` module: register, login, refresh (with rotation + reuse detection), logout, email verification, password reset.
- [ ] MFA: TOTP enrolment/verification, encrypted secrets, hashed recovery codes; enforced for admins.
- [ ] Per-tier response serializers wired to services.
- [ ] Optional RLS policies using `SET LOCAL`, plus the server-side role that bypasses them.
- [ ] Admin manual-provisioning path; audit-log writes on every admin/auth-sensitive action.
- [ ] Rate limiting on auth endpoints; CORS + secure headers.
- [ ] `tests/security`: authz, tenant isolation (with RLS off), tier filtering, gate enforcement, refresh rotation + reuse detection, revocation, account enumeration.
