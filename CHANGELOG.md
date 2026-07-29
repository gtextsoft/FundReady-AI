# Changelog

All notable changes to the FundReady API. The API contract is a product the mobile
developer builds on: additive changes are preferred, and any breaking change
requires a new API version **and** an entry here, shipped in the same change as the
code and the OpenAPI update (`CLAUDE.md` §6).

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- **Build queue corrected against the PRD, 2026-07-29** — a trace of PRD §4/§5 and
  `AUTH.md` against `TASKS.md` found six requirements with no task: the immutable
  audit log, email verification/password reset, MFA, admin user management, the
  founder AI chat, and the events catalogue. All are now queued (T1.1a, T1.2a–T1.2d,
  T3.7), along with deployment (T5.7). Email delivery moved from Phase 5 to Phase 1,
  because email verification gates sensitive actions from T1.2 and could not have
  worked otherwise. Decisions D17 (no `fastapi-users`) and D18 (one catalogue, events
  as a product type) recorded. No API change.
- **Stack change (`DECISIONS.md` D4, D13), 2026-07-29** — Neon (serverless Postgres +
  pgvector) replaces Supabase; authentication is now self-built in FastAPI (Argon2id,
  our own JWT access + rotating refresh tokens); uploads go to Cloudflare R2 and never
  to Postgres. Tenant isolation is now enforced primarily by service-layer ownership
  checks, with Postgres RLS as an optional second wall via a per-transaction setting.
  `AUTH.md` was rewritten accordingly. **No API endpoint changed** — no client impact
  yet, but the auth endpoints in `AUTH.md` §16 are what the mobile client will target.
- **`.env` keys changed** — the `SUPABASE_*` and `STORAGE_BUCKET_*` keys are gone,
  replaced by `JWT_*`, `ARGON2_*`, `MFA_SECRET_ENCRYPTION_KEY`, and `R2_*`. Because
  settings reject unknown keys, an old `.env` will refuse to start: re-copy from
  `.env.example`.

### Breaking
- **`POST /v1/auth/login` response shape changed (T1.2c).** It now returns a
  discriminated result instead of a bare token pair, because a user with MFA
  cannot be handed tokens on the password step alone:
  ```json
  {"status": "authenticated", "tokens": {"access_token": "...", "refresh_token": "...",
   "token_type": "bearer", "expires_in": 900}, "mfa_token": null}
  ```
  ```json
  {"status": "mfa_required", "tokens": null, "mfa_token": "<5-minute challenge>"}
  ```
  **Branch on `status`.** Tokens moved from the top level into `tokens`. Done now
  rather than after launch: the mobile app does not call `/v1/auth/login` yet, so
  the cost is zero today and only grows.

### Added
- Repository scaffold: module/layer structure per `ARCHITECTURE.md`, `pyproject.toml`,
  `.env.example`, README (T0.1). No API endpoints yet.
- Tooling and CI (T0.2): ruff (lint + format), mypy in strict mode, pytest, and a
  gitleaks secret scan, all wired into a GitHub Actions workflow that runs on every
  push and pull request. No API change.
- **`GET /v1/health`** (T0.3) — unauthenticated liveness check returning
  `{status, version, environment}`. The first endpoint on the API.
- **Error envelope** (T0.3) — every error response now returns
  `{"error": {"code", "message", "details"}}` with a stable, documented `code`.
  The full code table is in the README; the envelope is published in OpenAPI.
- **`X-Request-ID` header** (T0.3) — present on every response, including errors.
  A client-supplied value is honoured when it is a safe token, otherwise one is
  generated. On a `500`, the same id appears in `details.request_id`.
- Core scaffolding (T0.3): env-driven settings, async SQLAlchemy session
  management, and structured JSON logging with automatic secret redaction.
- **Two-factor authentication** (T1.2c) — TOTP, mandatory for admins.
  - `POST /v1/auth/mfa/enroll` — returns a base32 secret and an `otpauth://` URI
    for a QR code. **Does not enable MFA.**
  - `POST /v1/auth/mfa/confirm` — one valid code enables MFA and returns **ten
    recovery codes, shown once**. They are stored hashed and cannot be shown
    again. Re-enrolling invalidates the previous set.
  - `POST /v1/auth/mfa/verify` — exchanges the login `mfa_token` plus a TOTP code
    **or** one recovery code for tokens. A code cannot be replayed within its own
    30-second window, and a recovery code is spent permanently.
  - **Admins:** an admin who has not enrolled can log in but every admin
    capability returns `403` until they do — enrolling requires a session, so the
    second factor gates the power rather than the login.
- **Email verification and password reset** (T1.2b).
  - `POST /v1/auth/verify-email` — confirms the address and activates the account.
    The token arrives on a link pointing at **your app**, not this API: mail
    security scanners prefetch URLs and would consume a single-use token before
    the user clicked. Extract the token and POST it. Set `APP_LINK_BASE_URL`.
  - `POST /v1/auth/password-reset/request` — **always `202`**, whether or not the
    address is registered.
  - `POST /v1/auth/password-reset/confirm` — sets the new password and **ends
    every session**: all refresh tokens revoked, all access tokens invalidated,
    and any other reset link already sent is burned. The user re-logs in on every
    device.
  - Unknown, expired, already-used, and wrong-purpose tokens all return the same
    `422` — do not try to distinguish them.
- **Transactional email** (T1.2a) — internal only, no endpoint. Verification and
  password-reset messages over Resend. A send failure never propagates to the
  caller, so registration behaves identically whether or not email is working.
  Delivery not yet verified against a live provider.
- **Authentication endpoints** (T1.2) — the first real API surface. See `/docs`.
  - `POST /v1/auth/register` — founder or investor. **Returns `202` with the same
    body whether or not the address was already registered**, so the endpoint
    cannot be used to discover who has an account. Do not treat `202` as proof a
    new account exists. `admin` is rejected: admins are provisioned internally.
  - `POST /v1/auth/login` — returns `{access_token, refresh_token, token_type,
    expires_in}`. Every failure is the same `401` with the same message (unknown
    account, wrong password, or temporary lockout) — do not branch on it. `403`
    means suspended.
  - `POST /v1/auth/refresh` — **rotating**: the presented token is consumed and a
    new pair returned. Store the new refresh token and discard the old one
    immediately. **Presenting an already-used refresh token is treated as theft:
    every token from that login is revoked and all access tokens are
    invalidated.** Never retry a refresh with a token you already exchanged.
  - `POST /v1/auth/logout` — `204` always, even for an unrecognised token.
  - `GET /v1/users/me` — the caller's own account. Reachable while
    `pending_verification` so the client can prompt for verification; every other
    protected endpoint returns `403` until the email is verified.
- **Immutable audit log** (T1.1a) — the `audit_log` table, append-only and enforced
  by database triggers that reject UPDATE, DELETE, and TRUNCATE. Not yet exposed
  through any endpoint; `identity.service.record_action()` is the internal entry
  point other modules call. No API change.
- **Schema baseline** (T1.1) — Alembic configured and the first migration applied
  (`0001_baseline`, enabling `pgvector`). No tables yet. Adds the optional
  `DATABASE_MIGRATION_URL` setting for Neon's direct endpoint. No API change.
- **Auth foundation** (T0.4) — access-token verification and the role dependencies.
  No endpoint is protected yet, so there is no client-visible change, but the
  contract endpoints will follow is now fixed:
  - Send the access token as `Authorization: Bearer <token>`.
  - **`401`** = missing, invalid, or expired token → refresh once and retry. Every
    401 returns the *same* message regardless of cause, so do not branch on it.
  - **`403`** = authenticated but not permitted (wrong role, suspended account, or
    email not yet verified) → do not retry.
  - Role is resolved from our records on every request, never from a token claim,
    so a suspension or role change takes effect on the next call rather than at
    token expiry.
