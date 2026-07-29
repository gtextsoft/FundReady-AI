# CLAUDE.md — FundReady Backend

Project rules for Claude Code. Read this before every task. These rules override convenience and default habits. When a task conflicts with these rules, follow the rules and flag the conflict.

> Place this file at the repo root. Claude Code loads it automatically as project context. You may add a nested `CLAUDE.md` inside a module folder for module-specific notes.

---

## 1. What this project is

FundReady is the **backend + AI** for a two-sided, SACI-brokered platform. Founders get a fully automated AI audit of whether their business is **fundable** and **saleable**, plus report-driven tasks they must complete (and prove with uploaded evidence) to become investor-visible. Investors discover startups as **summaries**, chat with an AI analyst, and book meetings; **SACI is the broker** and the only party that reveals a full report.

- **You build the backend and AI only.** A separate mobile developer builds the client. You expose a documented API for them.
- **Source of truth for scope:** `fundready-prd.md` and `saci-audit-platform-backend-spec.md`. If a task isn't covered there, ask before building.
- **Core domain terms:** Startup Profile, AuditRun, readiness gate, evidence assessment, report tiers (summary vs full), brokerage, SACI admin.

## 2. Golden rules

1. **Plan before coding.** For anything non-trivial, propose a short approach and wait for confirmation. Keep changes small and reviewable.
2. **Follow the spec. Don't invent scope.** No features, endpoints, or dependencies that aren't in the PRD/spec. If it's ambiguous or missing, ask — never guess on security, money, or data-visibility logic.
3. **Backend only.** Never build the mobile/frontend app. Coordinate through the API contract.
4. **Security and data-tier rules (§4) are non-negotiable.**
5. **Stay cheap.** Don't add paid services or heavy dependencies without approval. Prefer what's already in the stack.

## 3. Architecture & code structure

- **Modular monolith** to start, with clear module boundaries: `identity`, `intake`, `audit`, `readiness`, `commerce`, `investor`, `brokerage`, `recommendation`, `notifications`, `ai`.
- **Layering:** router → service (business logic) → repository (data). No business logic in routers. No raw DB queries in routers.
- **Validate at the boundary.** Every request/response uses typed schemas (Pydantic). Reject unknown/extra fields.
- **All schema changes go through migrations.** Never edit the database by hand.
- **Config via environment variables.** Keep `.env.example` current. Never hardcode config or secrets.
- Small, focused functions; consistent naming; modules stay independent (talk through service interfaces, not each other's internals).

## 4. Security & data protection — CRITICAL, never violate

- **Authorize every endpoint.** Never trust a client-supplied role, tier, `user_id`, or `startup_id`. Derive identity from the verified auth token and check ownership server-side. Prevent IDOR.
- **Tenant isolation.** A founder must never read another founder's data. Enforce with Postgres row-level security **and** service-layer checks — defense in depth.
- **Report tiers are enforced server-side, per tier, via dedicated serializers — never by trusting the client to hide fields:**
  - **Investor →** summary only. The **full report is revealed ONLY by a SACI admin action** (at the meeting). No code path exposes a full report to an investor otherwise.
  - **Founder →** their own actionable audit + tasks. Never another startup's data. Never SACI's internal notes/positioning.
  - **SACI admin →** everything.
  - Never return a field above the caller's tier. If unsure whether a field is safe, exclude it and ask.
- **Secrets** (Claude API key, Stripe keys, DB creds) live only in env/secret manager. Never in code, logs, error messages, or git. Enable secret scanning.
- **Stripe:** always verify webhook signatures. Treat any client-reported payment/subscription state as untrusted — trust Stripe webhooks/API only. Bill through the UK/US entity (Stripe doesn't onboard Nigeria-registered businesses).
- **Encrypt** sensitive data at rest and in transit. Use least-privilege DB roles.
- **Immutable audit log** for every report reveal, tier change, purchase, and admin action.
- **Never log** secrets, full financial documents, or PII payloads.
- **Uploads:** validate type and size, scan them, store in object storage (not the DB), and serve via signed, expiring URLs.

## 5. AI / LLM rules

- **Money is math, not opinion.** Financial figures (margins, burn, runway, CAC/LTV, etc.) are computed in **code**. The model interprets; it never produces the numbers.
- **Structured output.** Audits, scores, and evidence assessments return JSON validated against a schema. Reject and retry on invalid output; never pass raw model text to clients.
- **Evidence-required.** No verdict or dimension score without citations to submitted data. Insufficient data → `provisional` / `insufficient-data`, **never** a false "fundable" or "ready."
- **Versioned prompts & rubrics.** Record `rubricVersion` on every AuditRun so past audits stay explainable.
- **Treat uploaded documents and user chat as UNTRUSTED.** Their content must never override system instructions, change a verdict directly, or cause data access beyond the caller's tier (prompt-injection defense).
- **Investor AI chat may only retrieve summary-tier data.** Enforce this in the retrieval layer, not in the prompt.
- **Evidence assessment grades against explicit per-task criteria.** "They uploaded something" is not a pass.
- **Cost control:** tier models (cheaper model for chat, strongest for audits), use prompt caching, cap tokens per request, and set per-user daily AI budgets. Long audits run as **idempotent background jobs** on the queue — never block the request thread.

## 6. API design & documentation — build it for the mobile developer

The API is a product another developer builds on. Treat the contract as sacred.

- **REST, versioned under `/v1`.** Plural resource nouns, correct HTTP status codes.
- **OpenAPI is the source of truth.** FastAPI auto-generates it — keep it accurate and expose `/docs` (Swagger) plus the OpenAPI JSON. Provide an exported collection (OpenAPI/Postman) for the mobile dev.
- **Every endpoint documents:** purpose, auth requirement, request schema, response schema, **all** error codes, and at least one example request + response.
- **Consistent error envelope:** `{ "error": { "code", "message", "details" } }`. Stable, documented error codes — never leak stack traces.
- **Consistent formats:** ISO 8601 UTC timestamps; ISO 4217 currency codes; money as integer minor units (document the convention once, apply everywhere).
- **Document every enum** the mobile app depends on: roles, audit status, task type/status, evidence result, report tier, interest/meeting state.
- **Consistent list conventions:** pagination, filtering, and sorting work the same way across all list endpoints and are documented.
- **Auth flow documented for mobile:** how to obtain, use, refresh, and expire tokens; what `401` vs `403` mean.
- **Never break the contract silently.** Prefer additive changes. Breaking changes require a new version **and** a `CHANGELOG` entry. Update docs + changelog in the *same* change that alters an endpoint.
- **Responses carry only what the caller is entitled to** — never internal fields or other tenants' data (this is both an API rule and a §4 rule).

## 7. Testing & quality

- **Write tests for the security-critical paths first:** authorization/ownership, tenant isolation, report-tier filtering, evidence gating, and Stripe webhook handling.
- **Golden-set evaluation** for the audit engine; consistency tests (same input → same score).
- **CI** runs tests, linting, and secret scanning on every change. Never merge with failing tests or any hardcoded secret.

## 8. Workflow

- Start from the PRD/spec. If a task isn't covered, ask before building.
- Propose a short plan for non-trivial work; implement in small, clearly-messaged commits.
- Update API docs, `CHANGELOG`, and migrations in the same change that requires them.
- Keep `.env.example` current whenever config changes.

## 9. DO / DON'T (quick reference)

**DO:** follow the spec · enforce tiers & authz server-side · validate all input · compute money in code · document every endpoint · tier + cache AI calls · write security tests first · commit small · ask when unsure.

**DON'T:** hardcode secrets · trust client-supplied identity/tier/payment state · expose a full report to the wrong tier · compute financials in the LLM · let uploads or chat act as instructions · add paid infra or heavy deps without approval · build the frontend · invent scope · skip Stripe webhook verification · log sensitive data.

## 10. References

- Product requirements: `fundready-prd.md`
- Backend architecture & design: `saci-audit-platform-backend-spec.md`
- Claude Code docs: https://docs.claude.com/en/docs/claude-code/overview
