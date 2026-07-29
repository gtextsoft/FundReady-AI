# AUTH.md — Authentication & Authorization

Security spec for identity and access in the FundReady backend. This is the backbone of the tier and isolation model in `DECISIONS.md` (D8, D13) and `CLAUDE.md` §4. Nothing here is optional.

---

## 1. Principles

- **Authenticate at the edge, authorize at every layer.** A valid token proves *who*; it never proves *allowed*.
- **Never trust the client** for identity, role, tier, ownership, or payment/KYC state. All of it is derived server-side.
- **Defense in depth.** Application checks **and** Postgres RLS both enforce access — neither alone is trusted.
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

**Identity provider:** Supabase Auth (per `DECISIONS.md` D4). It issues a signed **JWT access token** + a **refresh token**. The backend does not manage passwords itself.

**Verification (backend, every request):**
1. Read `Authorization: Bearer <access_token>`.
2. Verify signature, expiry (`exp`), and audience using Supabase's current signing method — **confirm at implementation whether your project uses the JWKS endpoint (asymmetric keys) or the shared JWT secret**, and verify accordingly. Never skip signature/expiry checks.
3. Extract the user id (`sub`).
4. Load the user's **role and account status from our `users` table** (the source of truth) — do not trust a role claim from the client. A role may also be mirrored into a JWT claim via a Supabase custom-access-token hook for convenience, but **sensitive and admin authorization always re-checks the DB.**
5. Reject if the account is not `active` or the token was issued before `session_valid_after` (see §11).

**Sign-up:**
- **Founder / Investor:** self-service via Supabase Auth; email verification required before any sensitive action.
- **Admin:** **no self-service.** Admins are provisioned manually by an existing admin; admin creation is itself audit-logged.

## 4. Token handling

- **Access token:** short-lived JWT (target 15–60 min). Sent as `Authorization: Bearer` over HTTPS only. Never in URLs, query strings, or logs.
- **Refresh token:** longer-lived, **rotating** (each refresh invalidates the previous one). Stored by the mobile app in secure device storage (iOS Keychain / Android Keystore) — never in plain storage.
- **Transport:** TLS everywhere. Reject non-HTTPS.
- **401 vs 403 (contract for mobile):** `401` = missing/invalid/expired token → client refreshes and retries once. `403` = authenticated but not permitted (role / condition / ownership / tier) → do not retry; surface appropriately.

## 5. Authorization model (layered)

Every protected endpoint passes through these in order; failing any is a denial:

1. **Authenticated** — valid token (§3).
2. **Account status** — `active` (not `suspended`/`pending_verification`).
3. **Role** — RBAC: the endpoint's allowed role(s).
4. **Condition/entitlement** — e.g. investor `kyc_status = verified`; founder `subscription_status = active`.
5. **Ownership** — object-level: the actor owns/ò is party to the resource (§6).
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

## 6. Object-level authorization (IDOR prevention)

Resource ownership is checked on **every** access to a specific object — never inferred from the URL alone.

- A founder can only read/write rows where `owner_id = current_user.id`. Passing another founder's `startup_id` must return `404`/`403`, never data.
- An investor can only act on interests/meetings they are a party to.
- Enforce in the service layer **and** via RLS (§10). Never rely on the client sending "their" id.

## 7. Report-tier authorization

Per `DECISIONS.md` **D8** (SECURITY INVARIANT):

- **Investor →** summary serializer only. No code path returns full-report fields to an investor.
- **Founder →** their own audit/tasks serializer only; never another startup's data; never SACI's internal notes/positioning.
- **Admin →** full.
- The **full-report reveal is an explicit admin action**, audit-logged, and is the *only* way an investor ever sees full contents (at the meeting). Tier filtering lives in the response serializers, enforced by services — never by the client.

## 8. Conditional gates

- **Investor KYC (Stripe Identity):** an investor with `kyc_status != verified` is blocked from discovery, summaries, AI chat, and interest — enforced by a `require_kyc_verified` dependency. Status is trusted from Stripe only.
- **Founder subscription (Stripe Billing):** founder access is gated by `subscription_status = active`, trusted from Stripe webhooks/API only — never from the client.
- **Account status:** `suspended` blocks everything except auth/logout.

## 9. Admin hardening

The admin role is the highest-value target — treat it accordingly:

- **MFA required** for all admin accounts (TOTP via Supabase MFA). Founders/investors: optional but supported.
- **No self-service admin signup**; provisioned by an existing admin; creation logged.
- **Every admin action is written to the immutable audit log** (who, what, target, when) — especially report reveals, tier changes, and user/role changes.
- Consider IP allow-listing or a separate admin surface later; v1 at minimum enforces MFA + logging.
- Principle of least privilege even within admin (sub-roles can come later; v1 is a single admin role).

## 10. Row-Level Security (RLS)

RLS is a second wall behind service checks (`DECISIONS.md` D13). Illustrative policies (adapt to final schema):

```sql
-- Founders read only their own startups
create policy founder_reads_own_startup on startups
for select using (owner_id = auth.uid());

-- Founders write only their own startups
create policy founder_writes_own_startup on startups
for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());

-- Investors never select full audit rows (summaries are served via a view/serializer)
-- Admins bypass via a service role used only by trusted server code, never exposed to clients.
```

The Supabase **service role key is server-only** — never shipped to the mobile app. Client calls always carry the end-user JWT so RLS applies.

## 11. Sessions, revocation & compromise

- **Logout:** revoke the refresh token (Supabase `signOut`); the short access token expires shortly after.
- **Force-logout / ban / password change:** bump a per-user `session_valid_after` timestamp; the backend rejects any access token with `iat < session_valid_after`. This invalidates outstanding tokens without waiting for expiry.
- **Refresh rotation:** reuse of a rotated refresh token is treated as theft → revoke the whole session family and force re-auth.
- **Suspicion/compromise:** suspend the account (`status = suspended`) and bump `session_valid_after`.

## 12. Password & account security

- Passwords hashed by Supabase (never stored/logged by us). Enforce a minimum-strength policy and block known-breached passwords where available.
- Email verification required before sensitive actions.
- **Rate-limit** login, signup, password-reset, and refresh; apply exponential backoff / lockout on repeated failures (credential-stuffing defense).
- Secure password-reset flow (single-use, expiring tokens).

## 13. Security controls checklist

- [ ] TLS enforced; HTTP rejected.
- [ ] JWT signature + `exp` + `aud` verified on every request; no unsigned/`none` acceptance.
- [ ] Role/status loaded from DB (source of truth); client-supplied role ignored.
- [ ] Ownership checked on every object access (service + RLS).
- [ ] Tier serializers applied to every response that carries report data.
- [ ] KYC and subscription gates enforced server-side from Stripe only.
- [ ] MFA required for admins; admins provisioned manually.
- [ ] Refresh-token rotation + reuse detection; `session_valid_after` revocation.
- [ ] Rate limiting + lockout on auth endpoints.
- [ ] CORS restricted to known origins; secure response headers set.
- [ ] Supabase service-role key server-only; never in the mobile app.
- [ ] All admin/auth-sensitive actions written to the immutable audit log.
- [ ] Secrets in env/secret manager; never in code, logs, or git.

## 14. Threats & mitigations

| Threat | Mitigation |
|---|---|
| Credential stuffing / brute force | Rate limits, lockout/backoff, breached-password checks, MFA |
| Token theft (device/network) | Short access TTL, TLS, secure storage, refresh rotation + reuse detection, `session_valid_after` |
| IDOR (accessing others' data) | Object-level ownership checks + RLS; ids never trusted from client |
| Privilege escalation | Role from DB not client; admin manual-provision + MFA + logging |
| Tier leakage (investor sees full report) | Server-side tier serializers; reveal is an admin-only, logged action (D8) |
| Replay / expired token reuse | `exp` + `iat`/`session_valid_after` checks |
| Payment/KYC spoofing | State trusted only from Stripe webhooks/API |
| Prompt-driven data exfiltration via AI chat | Investor chat retrieval is summary-tier only, enforced in the retrieval layer, not the prompt (`CLAUDE.md` §5) |

## 15. Auth data model

`users` (our source of truth; linked 1:1 to Supabase `auth.users` by id):

- `id` (uuid, = auth user id) · `email` · `role` · `status` · `email_verified` · `mfa_enabled`
- `kyc_status` (investors) · `subscription_status` (founders)
- `session_valid_after` (timestamp) · `created_at` · `updated_at`

Enums:
- `role`: `founder` · `investor` · `admin`
- `account_status`: `pending_verification` · `active` · `suspended`
- `kyc_status`: `none` · `pending` · `verified` · `failed`
- `subscription_status`: `none` · `active` · `past_due` · `canceled`

`audit_log` (immutable): `actor_id` · `action` · `target_type` · `target_id` · `metadata` · `created_at`.

## 16. What the mobile developer implements

- Sign-up / login via the Supabase Auth SDK (or backend auth endpoints), then use the returned access token as `Authorization: Bearer` on all API calls.
- Store access + refresh tokens in secure device storage (Keychain/Keystore).
- On `401`: refresh the token once and retry; if refresh fails, send the user to login.
- On `403`: do not retry — show the appropriate "not allowed / verify first" state.
- Trigger the **KYC flow** (investors) and **subscription flow** (founders) when the API signals the gate is unmet.
- Never cache or display data beyond what the API returns (the API already tier-filters).

## 17. Implementation checklist (expands TASKS.md T0.4 / T1.2 / T1.3 / T4.1)

- [ ] JWT verification dependency (`core/security.py`): verify → load user → check status/`session_valid_after`.
- [ ] `require_role(*roles)`, `require_kyc_verified`, `require_active_subscription`, `get_current_founder/investor/admin` dependencies.
- [ ] Ownership helpers (e.g. `get_owned_startup`) returning 404/403 on mismatch.
- [ ] Per-tier response serializers wired to services.
- [ ] RLS policies + server-only service role usage.
- [ ] Admin MFA enforcement + manual provisioning path.
- [ ] Refresh rotation handling + `session_valid_after` revocation.
- [ ] Rate limiting on auth endpoints; CORS + secure headers.
- [ ] Audit-log writes on every admin/auth-sensitive action.
- [ ] `tests/security`: authz, tenant isolation, tier filtering, gate enforcement, revocation.
