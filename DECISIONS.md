# DECISIONS.md — FundReady Backend

Why things are the way they are. **Do not silently change anything here.** If a task seems to require reversing a decision, stop and raise it — these were chosen on purpose. Add new decisions as they're made; never delete history.

Format: **Decision → Why → Constraint (what this means for the code).**

---

### D1 — Backend + AI only; the client is a separate mobile app
**Why:** a different mobile developer builds the client; our job is a clean, documented API.
**Constraint:** never build frontend/UI. The API contract (OpenAPI) is the deliverable and must stay stable and documented.

### D2 — Modular monolith, not microservices
**Why:** far cheaper and simpler to run and reason about at this stage; module boundaries let us split later if needed.
**Constraint:** don't introduce service meshes, separate deployables, or inter-service HTTP. Keep boundaries clean instead.

### D3 — Python + FastAPI
**Why:** best fit for AI orchestration and financial computation; auto-generates OpenAPI for the mobile dev.
**Constraint:** don't switch languages/frameworks without a decision entry.

### D4 — Neon (serverless Postgres + pgvector) · self-built FastAPI auth · Cloudflare R2 for files
> **Revised 2026-07-29.** Supersedes the original D4 (Supabase for Postgres + Auth + Storage + pgvector), preserved at the bottom of this entry.

**Why:** an à la carte stack was chosen over a single-vendor BaaS for **full control of the custom auth/role/tier/broker logic** — the report-tier and brokerage rules (D8) are the heart of the product and don't fit a managed auth provider's model — and to avoid vendor lock-in. Cost stays comparable; every piece sits on a cheap or free tier. Neon scales to zero and carries pgvector, so search needs no separate vector database. Neon is a database, not a file store, so uploads go to R2, which has zero egress fees — the right economics for a file-heavy workload.

**Constraint:**
- **Do not reintroduce Supabase, or any managed auth provider.** Not Better Auth either (TypeScript-only; this is a Python service).
- **Do not add a separate vector database** (Pinecone, etc.). pgvector inside Neon covers it.
- **Files are never stored in Postgres.** Decks, financials, and evidence live in R2 and are served via signed, expiring URLs.
- Auth is ours to build and ours to get right: Argon2id password hashing, our own JWT access tokens, rotating refresh tokens with reuse detection. See `AUTH.md`.
- Changing any of these three is a new decision entry, not a refactor.

**Previously (superseded 2026-07-29):**
> **D4 — Supabase (Postgres + Auth + Storage + pgvector); pgvector for search.**
> *Why:* one low-cost vendor covers four needs; row-level security gives tenant isolation; pgvector avoids paying for a separate vector DB.
> *Constraint:* don't add a separate vector database (Pinecone, etc.) or a second auth system without a decision entry.

### D5 — Stripe as the payment gateway, billed through the UK/US entity; no Stripe Connect in v1
**Why:** Stripe doesn't onboard Nigeria-registered businesses directly. The platform mainly *collects* money (subscriptions + product fees) into SACI's account rather than paying out to many sellers, so Connect isn't needed yet.
**Constraint:** don't wire Connect/marketplace payouts in v1. Don't attempt a Nigeria-entity Stripe account. Revisit only if investor↔founder money moves on-platform (would tie into the escrow platform).

### D6 — Audit is fully automated; no human review
**Why:** scale. Trust comes from guardrails, not a human in the loop.
**Constraint:** rely on evidence-required prompting, provisional status on thin data, versioned rubrics, and golden-set evaluation. Internal QA is sampling only, not a gate.

### D7 — Internal-consistency check only; no external/bank verification in v1
**Why:** keeps v1 shippable. Consistency catches contradictions across a founder's own docs; it does not verify the numbers are true.
**Constraint:** everywhere audits are consumed, they are labelled **self-reported, consistency-checked** — never "verified." Carry a separate data-integrity signal. A "verified" badge is a future feature, not v1.

### D8 — Report tiers are enforced server-side; only a SACI admin reveals a full report
**Why:** this is the platform's core trust and confidentiality guarantee. A leak here kills the marketplace.
**Constraint (SECURITY INVARIANT):** investors get summary only; founders get their own audit only; SACI gets everything. Tier filtering lives in serializers, enforced by services — never trust the client. No code path reveals a full report to a non-admin. Do not relax this to "simplify" an endpoint.

### D9 — Financial figures are computed in code, never by the LLM
**Why:** accuracy and reproducibility. The model interprets; it must not invent numbers.
**Constraint (INVARIANT):** all math lives in `audit/finance.py`. Never ask the model to output a computed financial figure as ground truth.

### D10 — Readiness is earned by doing the task + uploading evidence + AI assessment + re-audit — NOT by purchasing
**Why:** purchase-gating would make this pay-to-play, which erodes investor trust and collapses the two-sided value. Buying a program is how a founder *accesses* help; evidence is what advances them.
**Constraint:** never simplify the gate to "purchase = unlocked." Required tasks must map to real audit gaps. Evidence must be graded against explicit per-task criteria; "uploaded something" is not a pass.

### D11 — Universal-core + adaptive rubric to support all sectors, including new ones
**Why:** the platform accepts any sector, even ones that don't exist yet; a fixed per-sector rubric can't cover that.
**Constraint:** keep universal core dimensions + an adaptive layer. When no benchmark exists (novel sector), reason from first principles/nearest analogue and **lower confidence + flag it** — never invent a benchmark.

### D12 — Rubrics and prompts are versioned
**Why:** audits must stay explainable after the rubric changes.
**Constraint:** record `rubricVersion` (and prompt version) on every `AuditRun`. Never mutate a published rubric version in place — add a new one.

### D13 — Tenant isolation: app-layer ownership checks are the PRIMARY wall; RLS via a per-transaction GUC is an OPTIONAL second wall
> **Revised 2026-07-29.** Follows from the D4 revision and supersedes the original D13, preserved at the bottom of this entry.

**Why:** founders' data is sensitive and competitive; one bug must not expose it. The original design leaned on Postgres RLS keyed to a managed `auth.uid()`. With self-built auth (D4) that function does not exist — the database has no independent notion of who the caller is, because the application is the only thing that verified the token. RLS can therefore no longer be the first line of defence: it can only enforce what the application tells it. So the ordering inverts.

**Constraint:**
- **The app-layer ownership check is mandatory on every object access.** A founder reads and writes only rows they own; an investor acts only on interests and meetings they are party to. This is enforced in the **service layer**, never in a router, and never inferred from an id supplied by the client.
- **RLS is optional and secondary.** Where it is used, the caller's identity is passed per transaction via a Postgres setting (`SET LOCAL app.current_user_id = ...`) and policies read it with `current_setting(...)`. Because the application sets that value, RLS is a **backstop against a missing app-layer check, not a substitute for one.**
- A missing app-layer check is a security bug even if RLS would have caught it.
- `tests/security` must prove a founder cannot read another founder's rows **by any path** — including with RLS disabled, since RLS is not the primary wall.

**Previously (superseded 2026-07-29):**
> **D13 — Tenant isolation via RLS + service-layer checks (defense in depth).**
> *Why:* founders' data is sensitive and competitive; one bug shouldn't expose it.
> *Constraint:* both layers required — don't rely on RLS alone or app checks alone. Security tests cover this path.

### D14 — Long audits run as idempotent background jobs
**Why:** audits are slow and token-heavy; they must not block the API or double-charge on retry.
**Constraint:** audit/evidence work runs on the worker via the queue and must be safe to retry. Don't run them inline in a request.

### D15 — Startup database starts empty; sequence founder-side first
**Why:** two-sided cold-start — investors won't come to an empty catalogue.
**Constraint:** build and populate the founder/audit side before opening investor discovery. Don't assume a pre-seeded database.

### D16 — AI cost is controlled by model tiering + prompt caching + budgets
**Why:** keep running cost low (a stated requirement).
**Constraint:** cheaper model for chat, strongest for audits; cache prompts; cap tokens per request; enforce per-user daily AI budgets. Watch per-audit cost from day one.

### D17 — Auth is hand-rolled against `AUTH.md`; `fastapi-users` is not used
*Recorded 2026-07-29. Follows from D4 (self-built auth).*
**Why:** the PRD listed `fastapi-users` as optional. It was evaluated and declined: it brings its own user model and router conventions that cut across the role/tier/broker logic — which is the heart of this product, not boilerplate — and against the `router → service → repository` boundary in `ARCHITECTURE.md` §3. It would also not supply the control that matters most here, refresh-token **family revocation on reuse** (`AUTH.md` §4.2), so the security-critical part would be hand-written regardless.
**Constraint:** implement auth directly against the `AUTH.md` spec. Don't adopt an auth framework later without a new decision entry — the cost of migrating a live user table is the thing being avoided.

### D18 — One catalogue; events are a product type
*Recorded 2026-07-29.*
**Why:** the PRD describes programs, mentorship, and events as things SACI lists and sells. They share everything that matters — tags, region relevance, pricing, Stripe Checkout, and the link from a readiness gap to a purchase. A separate events module would duplicate all of it to model a difference that is really just two extra fields.
**Constraint:** a single catalogue model with a type discriminator (`program` · `mentorship` · `event`); events carry date and location. One admin CRUD, one purchase path. Splitting them later is a new decision entry.

### D19 — RLS is deferred to T5.7 behind a least-privilege role, because `neondb_owner` carries `BYPASSRLS`
*Recorded 2026-07-30. Scopes the RLS half of D13; does not change it.*

**Why:** T1.3 set out to add the optional RLS backstop D13 describes. Probing the live Neon database showed it cannot work as configured:

```
current_user = neondb_owner    rolsuper = false    rolbypassrls = TRUE
all 7 public tables owned by neondb_owner, rowsecurity = false, 0 policies
```

A role holding `BYPASSRLS` skips row-level security on every table unconditionally. This is stronger than the familiar table-owner caveat: `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` are **both** no-ops for such a role. Writing the policies now would produce SQL that appears in `pg_policies`, reads as protection in a review, and enforces nothing — worse than no RLS, because the second wall would be believed to exist.

Making it real needs a second Postgres role (`NOBYPASSRLS`, least privilege, not the table owner) with `DATABASE_URL` pointed at it while `DATABASE_MIGRATION_URL` stays on the owner. That is Neon provisioning plus `core/config.py`, `.env.example`, and `tests/conftest.py` — the same ground T5.7 already covers, and pointless to do twice.

**Constraint:**
- The app-layer ownership check (`core/ownership.py`) is, for now, the **only** tenant-isolation wall. D13 already called it the primary one; until T5.7 there is nothing behind it. Treat a missing ownership check accordingly.
- **T5.7 provisions the role and adds the policies migration.** Enabling RLS without a `NOBYPASSRLS` connection role is not a partial win, it is a false one.
- Any future test asserting RLS enforcement must run as a non-owner, non-bypassing role, or it proves nothing.

### D20 — Founders register on a company email; the domain seeds the company name
*Recorded 2026-07-30. New scope, requested by the product owner; not in the PRD.*

**Why:** a company address is a cheap signal that a founder is registering a real business rather than browsing, and the domain is a free, already-verified source for the one profile field the platform would otherwise ask them to type first. Verification is real: an account sits at `pending_verification` until the emailed link is clicked, so by the time any profile exists the founder has demonstrably controlled a mailbox at that domain.

**Constraint:**
- **Founders only.** Investors are exempt — an angel investing personally has no company domain, and `AUTH.md` §8's KYC gate is what establishes an investor's identity.
- The refusal is **explicit** (`422`, `details.reason = "consumer_email_domain"`), not folded into registration's uniform response. The uniform response exists to hide *account existence*; this answer concerns the domain the caller just typed and leaks nothing. Answering uniformly would leave a founder waiting for an email that would never arrive.
- Checked **before** the duplicate lookup, so a refused signup writes nothing.
- **The blocklist is a heuristic, not a security control.** It cannot enumerate every consumer provider, and passing it proves nothing about corporate identity — a domain costs a few pounds. Never treat "has a company domain" as verification that a company exists or that this person belongs to it.
- The derived company name is a **prefill**. It is written only when the founder supplies no name, never overwrites one they did supply, and is `None` rather than a guess when nothing sensible can be read. Nothing downstream may treat it as a legal name.

**The tradeoff, accepted knowingly:** this product's own vocabulary includes `Stage.IDEA` and `PRE_SEED` (`intake/fields.py`), and the PRD's premise is converting not-yet-ready startups. Idea-stage founders frequently have no company domain, and a hard block at registration turns them away at the one step where a rejected user simply leaves. The alternative considered was requiring the company address at **profile creation** instead, which preserves the funnel and still guarantees every profile has a verified company domain behind it. The owner chose the hard block at registration. **If signup conversion for early-stage founders disappoints, moving the check to profile creation is the first thing to try** — the rule is one call in `register_user` and the derivation is untouched by the move.
