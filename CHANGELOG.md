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
