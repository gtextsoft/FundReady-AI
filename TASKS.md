# TASKS.md — FundReady Backend

The build queue. **Do one task at a time**, top to bottom — point the AI at a single task per session, let it finish (code + tests + docs), check it off, then move on. Don't skip ahead. If a task is unclear, refine it here before building. Acceptance notes are the bar for "done."

Legend: `[ ]` todo · `[x]` done · `[~]` in progress

---

## Phase 0 — Project setup

- [x] **T0.1 Scaffold repo** to the layout in `ARCHITECTURE.md`; add `pyproject.toml`/`requirements.txt`, `.env.example`, `README`. *Done when: structure exists and the app imports cleanly.*
- [x] **T0.2 Tooling & CI** — ruff, mypy, pytest configured; CI runs lint + types + tests + secret scan on every push. *Done when: CI is green on an empty test.*
- [x] **T0.3 Core scaffolding** — `core/config.py` (env-driven), `core/db.py` (session), `core/errors.py` (error envelope + handlers), `core/logging.py`, a `/v1/health` endpoint. *Done when: health returns 200 and errors use the envelope.*
- [ ] **T0.4 Auth foundation** — token verification dependency, `current_user`, role/tier extraction, RBAC dependency. *Done when: a protected test route rejects missing/invalid tokens with 401 and wrong-role with 403.*

## Phase 1 — Foundations

- [ ] **T1.1 Alembic setup** and base migration. *Done when: `alembic upgrade head` runs on a clean DB.*
- [ ] **T1.2 Identity + auth module** — user model, roles (founder/investor/admin), self-built auth per `AUTH.md` (Argon2id hashing, JWT access+refresh, refresh rotation). *Done when: users can register, log in, and refresh; roles persist.*
- [ ] **T1.3 Tenant isolation** — app-layer ownership checks (primary) + optional Postgres RLS via a per-transaction user setting (GUC). *Done when: `tests/security` prove a founder cannot read another founder's rows via any path.*
- [ ] **T1.4 Startup Profile** — model + schemas; create/update endpoints with ownership checks; `source`/`confidence` per field and `missingFields`. *Done when: a founder can create/update only their own profile.*
- [ ] **T1.5 Document upload** — signed upload/download URLs to object storage; type/size validation; scan hook. *Done when: uploads are stored out of the DB and served via expiring URLs.*

## Phase 2 — Audit engine

- [ ] **T2.1 AI client** — `ai/client.py` with model tiering, structured-output validation, retry-on-invalid, prompt versioning, injection guards. *Done when: a call returns schema-valid JSON or fails cleanly.*
- [ ] **T2.2 Finance module** — `audit/finance.py` deterministic calculations + currency normalization. *Done when: unit tests cover the core ratios; no LLM involved.*
- [ ] **T2.3 Benchmark KB** — model + admin CRUD keyed by sector × stage × metric × region with source/date. *Done when: benchmarks can be created and queried.*
- [ ] **T2.4 Extraction stage** — documents → Startup Profile fields with source/confidence and missing-field flags. *Done when: a sample deck+financials populate the profile.*
- [ ] **T2.5 Consistency check** — cross-document contradiction detection → `dataIntegrityScore` + contradiction list. *Done when: a planted contradiction is flagged.*
- [ ] **T2.6 Rubric v1** — universal core + adaptive layer; saleability rubric; explicit criteria; versioned. *Done when: `rubric/v1` scores a profile with citations.*
- [ ] **T2.7 Scoring + synthesis** — dimensional scoring → verdicts (fundable/saleable) + founder report + action plan; provisional on thin data. *Done when: a full report is produced and grounded in stages 2.4–2.6.*
- [ ] **T2.8 AuditRun persistence** — model, `rubricVersion`, embeddings; `run_audit` background job + queue; status endpoint. *Done when: submitting a profile runs an async audit and status is pollable.*
- [ ] **T2.9 Golden-set harness** — evaluate audits against hand-scored companies; consistency test (same input → same score). *Done when: an eval report is produced and repeatable.*

## Phase 3 — Readiness loop

- [ ] **T3.1 Task generation** — required/recommended tasks from audit gaps, specific to the report; link to products where relevant. *Done when: gaps produce correct required vs recommended tasks.*
- [ ] **T3.2 Product catalogue** — model + admin CRUD; tags + region relevance. *Done when: products can be listed and matched to gaps.*
- [ ] **T3.3 Stripe checkout** — purchase products via Checkout; webhook signature verification; purchase records link to tasks. *Done when: a verified webhook marks a purchase and links its task.*
- [ ] **T3.4 Founder subscription** — Stripe Billing lifecycle; subscription gates founder access. *Done when: subscription state is trusted from Stripe only.*
- [ ] **T3.5 Evidence upload + assessment** — upload evidence; `assess_evidence` job grades against per-task criteria → pass/fail/needs-more. *Done when: weak evidence fails with reasons; strong evidence passes.*
- [ ] **T3.6 Re-audit + gating** — passing evidence re-audits affected dimensions; investor-visibility gate = audit cleared AND required tasks passed; dispute/re-audit path. *Done when: a startup only becomes investor-visible after the gate is satisfied; `tests/security` prove it.*

## Phase 4 — Investor side & brokerage

- [ ] **T4.1 Investor profile + KYC** — thesis capture; Stripe Identity gate before discovery. *Done when: un-KYC'd investors cannot discover startups.*
- [ ] **T4.2 Summary serializer** — investor-facing summary tier; `tests/security` prove no full-report field leaks. *Done when: summaries never contain internal/full fields.*
- [ ] **T4.3 Discovery + ranking** — filter/rank investor-ready startups against thesis. *Done when: results respect visibility and thesis.*
- [ ] **T4.4 Investor AI chat** — analyst chat restricted to **summary-tier retrieval** (enforced in retrieval, not the prompt). *Done when: the chat cannot surface data above summary tier even when prompted to.*
- [ ] **T4.5 Interest → SACI approval → meeting** — interest expression; admin approval workflow; meeting scheduling with SACI as required participant. *Done when: an interest moves through the states with SACI in the middle.*
- [ ] **T4.6 Full-report reveal** — admin-only reveal action, logged immutably. *Done when: only an admin action reveals a full report and it's audit-logged.*

## Phase 5 — Depth & hardening

- [ ] **T5.1 Per-country benchmarks & recommendations** — region-aware benchmark lookup and program matching.
- [ ] **T5.2 Recommendation surfacing** — gap→program in both chats + browsable catalogue, filtered per country.
- [ ] **T5.3 Notifications** — transactional emails (audit ready, task assigned, evidence result, meeting booked).
- [ ] **T5.4 Analytics/metrics** — the success metrics from the PRD.
- [ ] **T5.5 Hardening** — rate limiting, per-user AI budget caps, monitoring/alerting, security review.
- [ ] **T5.6 API docs polish** — complete OpenAPI, exported collection, and `CHANGELOG` for the mobile developer.

---

### Open follow-ups
- [ ] **Push to a remote and confirm CI is actually green** — closes the last part of T0.2. `.github/workflows/ci.yml` has never executed; only its commands have been verified, locally.
- [ ] **Retire the Supabase settings in `core/config.py` and `.env.example`** — replace with Neon + R2 keys and self-built JWT signing (T0.3a).
- [ ] **Missing document:** `saci-audit-platform-backend-spec.md` is referenced by `CLAUDE.md` §1 and §10 but is not in the repo — needed before Phase 2.

### Backlog / open questions (resolve before the dependent task)
- [ ] Confirm founder report visibility (full actionable audit vs summary) — affects T2.7, T4.2.
- [ ] Evidence strictness + resubmission limits — affects T3.5.
- [ ] Data residency across NG/UAE/UK/US/China — affects T1.5, storage.
- [ ] On-platform investor↔founder transactions (escrow integration) — affects D5/T3.3 scope.