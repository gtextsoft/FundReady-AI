# Changelog

All notable changes to the FundReady API. The API contract is a product the mobile
developer builds on: additive changes are preferred, and any breaking change
requires a new API version **and** an entry here, shipped in the same change as the
code and the OpenAPI update (`CLAUDE.md` §6).

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **`AuditRun` persistence and migration `0010`, 2026-08-02 (T2.8, partial).**
  One row per execution of the audit pipeline, carrying `rubric_version` (D12)
  so a verdict stays explainable after the rubric moves on. **No API change** —
  no endpoint reads or writes this table yet.
  - **`uq_audit_runs_idempotency` on `(startup_id, input_hash, rubric_version)`
    is the point of the table.** D14 requires a repeated run to be safe, and an
    audit is the most expensive call the platform makes (`claude-opus-5`, high
    effort, 16k budget), so a duplicate is a real charge for a verdict the
    founder already has. The constraint closes the race an RQ `job_id` cannot:
    a job id prevents a duplicate only while the job is in flight and lapses
    the moment it finishes. Four integration tests against the real database
    prove the `IntegrityError`, that a new `rubric_version` is still allowed,
    and that changed inputs still produce a fresh run.
  - **`input_fingerprint` must be computed from the persisted JSONB.**
    `startup_profiles.fields` round-trips through Postgres, so a value written
    as `Decimal("42.5000")` reads back as `42.5` and hashes differently —
    which would bill a founder twice for one audit. One code path, documented
    at the function.
  - **No embedding column, though the task lists embeddings.** Anthropic has no
    embeddings endpoint and a vector's dimension is provider-specific (1024,
    1536, …), so declaring one would silently commit to a provider nobody has
    chosen. `pgvector` remains a declared and unused dependency. Filed as an
    open follow-up; adding the column later is one additive migration.
  - Applied to Neon and verified with `alembic check` (no drift). Still `[~]`:
    `REDIS_URL` is blank so no job has ever been dispatched, `pipeline.py` is
    still a docstring, and the status endpoint is not built.

- **`CLIENTS.md` — the client integration guide, 2026-08-01.** One document for
  the **three roles across two surfaces**: founders and investors on mobile,
  SACI admins on web. Covers the auth lifecycle (including refresh rotation and
  reuse detection, the single easiest thing for a client to get wrong), the
  `401` vs `403` distinction, the error envelope and every stable code, the
  three-step document upload, every enum a client switches on, and an explicit
  **"not built yet"** list so nobody codes against Phase 3–5.
  *No API change — this documents what already exists.*
  - **`docs/openapi.json` is now committed**, so a client developer can
    generate a typed client or diff an API change without running the service.
    Regenerate with `python scripts/export_openapi.py`.
  - **Two corrections it makes to previously-stated behaviour:** all five
    `/v1/benchmarks` endpoints are **admin-only including the reads** (a
    founder who could read the bands would know exactly what to claim), and
    `first_name`/`last_name` are nullable on `UserResponse` for provisioned
    admins and pre-column accounts.
  - `tests/unit/test_client_guide.py` fails if a path or enum value the guide
    names stops existing, or if the exported spec goes stale. Prose still needs
    a human; the contract does not.
- **Scoring and synthesis (T2.7), 2026-08-01 — scores to verdicts, report, and
  action plan.** **No API change and no new endpoint**; stage 5, reachable once
  T2.8 wires the pipeline.
  - **The verdict is computed by rule, not asked of a model.** The inputs came
    from one, but the verdict itself must be reproducible (T2.9), explainable
    to the founder who receives it, and incapable of being talked out of
    `CLAUDE.md` §5's ban on a false "fundable" on thin data.
  - **Four levels: `ready`, `not_yet`, `provisional`, `insufficient_data`.**
    *Client impact once T2.8 lands: `insufficient_data` is an **absence, not a
    failure** — never render it as "not fundable". `provisional` must always be
    shown labelled as such, never as a plain result. Branch on `level`; the
    `rationale` is prose and will change.*
  - Coverage below half the in-scope dimensions yields `insufficient_data`
    however good the available evidence looks, and a `data_integrity_score`
    under 50 blocks the verdict outright — scoring figures we already believe
    are wrong is scoring noise.
  - The action plan derives from the rubric's `unmet_criteria`, sorted with
    unassessable dimensions first, then worst-scoring: those are cheaper to fix
    and they are what blocks the verdict.
- **Consistency check (T2.5), 2026-08-01 — does the submitted data agree with
  itself?** **No API change and no new endpoint**; stage 2 of the pipeline,
  reachable once T2.8 wires it up.
  - **Scale plausibility is arithmetic, in code — not a model call.** D9 says
    money is math, and a model judging it would break T2.9's
    same-input-same-score requirement. Contradiction detection *is* the model's
    half, and must cite both conflicting claims.
  - **Thresholds are deliberately loose: 10x, never 2x.** A false positive
    costs more than a missed subtlety — telling a founder their revenue looks
    wrong when it is right damages trust in the whole audit. A 3x discrepancy
    is explicitly not reported; a business that grew or shrank is normal.
  - **Churn is judged against customer count, not range.** `0.02` meaning 2% is
    indistinguishable from a genuine `0.02%` on range alone (T2.2a), so the
    test is whether the rate describes fewer than one customer a month. At
    50,000 customers 0.02% is ten people — real. At 34 it is 0.0068 — a typo.
  - **Findings carry a founder-facing `message` and an engineer-facing
    `detail`, and `log_context()` carries neither.** Logs get the code,
    severity, and field names only — never figures (`CLAUDE.md` §4). Showing a
    founder their own numbers is not a leak; writing them to a shared log is.
    Founder messages are also tested to be non-accusatory: a mistyped unit is
    far likelier than dishonesty. *Client impact once T2.8 lands: expect a
    `data_integrity_score` (0–100) and a findings list whose `code` is stable
    and safe to branch on; `message` is prose and will change.*
- **Extraction stage (T2.4), 2026-08-01 — documents to Startup Profile fields.**
  **No API change and no new endpoint**: this is stage 1 of the audit pipeline,
  invoked by the background job that lands with T2.8. Nothing is reachable over
  HTTP yet.
  - **PDFs and images are sent to the model as native `document`/`image`
    blocks, not text-extracted.** A pitch deck is a design artefact — a text
    extractor returns the speaker notes and misses the chart carrying the
    number — and a photographed cap table has no text layer at all. This also
    means **no PDF dependency was added**.
  - **Three parsers added for the Office formats the API cannot ingest
    natively** (approved 2026-08-01): `openpyxl` (xlsx), `python-pptx` (pptx),
    `python-docx` (docx), plus `types-openpyxl` for strict typing. All pure
    Python, no system binaries. The **legacy binary formats — `.xls`, `.ppt`,
    `.doc` — stay on the upload allowlist but cannot be read**; those uploads
    are reported in `unreadable` so a founder learns which file was wasted
    rather than wondering why a field stayed empty.
  - **A founder-stated value is never overwritten by an extracted one.**
    Extraction fills gaps and corrects nothing; silently replacing what someone
    typed with what a model read off a slide is the fastest way to lose their
    trust in the audit. *Client impact once T2.8 wires this up: a profile field
    may arrive with `source: "document"`, a `confidence`, and a `citation` — a
    value the founder never typed. Show `confidence` below 0.5 as provisional.*
  - Extraction **records, never computes**. Ratios, runway, and margins remain
    `audit/finance.py`'s job, in code (D9). A value here is a reading; a
    calculated one arriving as a reading would be a false reading.
  - Every extracted value carries a citation to the document and the quoted
    span, and anything failing its `FieldSpec` is dropped rather than stored.
- **`GET /v1/benchmarks` filtering and paging documented, 2026-08-01.** The
  endpoint has always accepted `sector`, `stage`, `metric`, `region`,
  `include_retired`, `limit`, and `offset` — all optional — but none of it was
  written down anywhere. **No API change**; this documents existing behaviour.
  - **The two list endpoints do not share conventions**, which `CLAUDE.md` §6
    requires them to. `GET /v1/benchmarks` takes the seven parameters above;
    `GET /v1/startups/{startup_id}/documents` takes **none** and returns every
    row. Neither supports sorting, and neither returns a total count, so a
    client cannot render "page 3 of 12" — only a cursor-style "load more".
    *Client impact: a generic list helper written against one endpoint will be
    wrong for the other.* Documented in `CLIENTS.md` §3 and filed as an open
    follow-up rather than silently normalised, because adding paging to
    `documents` changes a response shape the mobile client already consumes.

### Changed
- **Failed AI calls now report what they cost, 2026-08-01.** `AiError` carries
  an `AiUsage` on `.usage`, populated on every billed failure — refusal,
  truncation, and invalid output alike — and `complete` folds earlier attempts
  in before re-raising, so a refusal on the retry reports both attempts rather
  than half the bill. **No API change**; this is internal to `ai/client.py`.
  *Why it mattered:* the three most expensive calls the platform can make are
  all failures — a truncated audit runs to the full 16k cap at high effort, and
  a mismatch retry bills twice — so the T5.5 per-user budget was set up to
  under-count precisely the spend it exists to cap.
  - **Billed tests are now gated behind a `billed` pytest marker**, deselected
    by default via `addopts`. `tests/integration/test_ai_live.py` skips without
    a key, which protects an *unconfigured* machine but not a configured one:
    adding `ANTHROPIC_API_KEY` to CI would otherwise have started spending real
    money on every push. Running them is now deliberate — `pytest -m billed`.
- **⚠️ BREAKING — `POST /v1/auth/register` now requires `first_name` and
  `last_name`, 2026-07-30.** Both are collected for **founders and investors**
  alike. A registration body without them is rejected with **`422`**.
  *Client impact: any existing call to this endpoint breaks until the two
  fields are added.* No API version bump was made — this endpoint has no
  released consumers yet.
  - **Answered 2026-07-31: the mobile client IS calling this endpoint, and it
    is broken right now.** `frontend/src/api/index.ts` points at the live API
    with no mock, and `signUp` in `frontend/src/api/http.ts` deliberately omits
    both fields — its own comment says *"the register schema rejects unknown
    fields… Add the two lines back the moment the backend accepts them."* That
    moment has arrived, so every mobile registration currently gets a `422`.
    **No `/v2` is proposed:** the endpoint has no *released* consumers, the
    client already collects and validates both names on its sign-up screen, and
    the fix is the two lines its author left a note to restore. Versioning an
    unreleased endpoint would cost the mobile developer more than the two-line
    change it exists to spare them. **Owner's call** — say so and `/v2` is the
    alternative. Either way the mobile developer needs telling today.
  - Validation is deliberately permissive about **what a name may contain**:
    1–100 characters, whitespace trimmed, control characters stripped, and **no
    alphabet restriction**. Diacritics, non-Latin scripts, apostrophes, spaces,
    hyphens, and single characters are all accepted — `Ọláwálé`, `O'Brien`,
    `van der Berg`, `李`, and `محمد` are valid. A letters-only rule would reject
    real names across the regions this platform serves.
  - `UserResponse` gains `first_name` and `last_name`, and **both are
    nullable** — admins are provisioned rather than self-registered, and
    accounts predating this change never supplied one. Clients must handle
    `null`.
  - Stored as one pair of columns on `users`, distinguished by the existing
    `role`, so a founder's name and an investor's name are never confusable.
    `startup_profiles.name` remains the **company** name and is unchanged.
  - The name is **not** written to the audit log: that table is append-only, so
    PII placed there could never be corrected or erased. `actor_id` already
    records who registered.
  - Migration `0009_user_names`, verified up and down.
- **Profile field values are now validated against their declared kind
  (T2.2a), 2026-07-30.** `POST /v1/startups` and `PATCH /v1/startups/{id}`
  return **`422`** naming each offending field when a value contradicts its
  `FieldKind`: a `percent` outside 0–100, a `money_minor` that is not a whole
  number, a negative count or amount, an implausible `year`, or a boolean where
  a number belongs. Previously the kinds were documentation and anything
  scalar stored. All problems in one payload are reported together, not one per
  round trip. *Client impact: a form sending `45000.50` for a money field, or a
  percentage as a fraction, will now be rejected — send integer minor units and
  0–100 percentages.*

### Added
- **Audit rubric v1 (T2.6), 2026-07-30.** `audit/rubric/v1` — 11 scored
  dimensions with explicit criteria, versioned and immutable once published.
  **No endpoint or contract change:** internal, and not yet reachable from the
  API (scoring is wired up in T2.7/T2.8).
  - Seven universal-core dimensions apply to both verdicts; `scalability` is
    fundability-only; `owner_independence`, `transferability`, and
    `revenue_durability` are saleability-only.
  - Every score carries citations to the submitted data. A dimension with
    nothing to go on returns `insufficient_data` rather than a low score —
    absent and bad are never collapsed.
  - When no benchmark matches, the rubric reasons from first principles and
    lowers confidence. It never invents a band (D11).
  - Financial figures arrive pre-computed from `audit/finance.py`; the prompt
    marks them authoritative and forbids recomputation (D9).
  - Recorded on every AuditRun as `rubric_version` `v1` plus prompt ref
    `audit_scoring@1`, so a past audit stays explainable (D12).
- **AI client with model tiering (T2.1), 2026-07-30.** `app/ai/` — the single
  chokepoint for every Claude API call. **No endpoint or contract change:** this
  is internal plumbing the audit engine (T2.4–T2.7) and chat (T4.4) build on,
  and nothing in it is reachable from the API yet.
  - Audits run on the strongest model at high effort, chat on a cheaper model at
    low effort (D16). `AI_MODEL_AUDIT` / `AI_MODEL_CHAT` override per
    environment; `AI_MAX_OUTPUT_TOKENS` is a **ceiling** over both tiers.
  - Responses are validated against a schema before anything downstream sees
    them. A refusal and a truncation each fail immediately; only a schema
    mismatch is retried, once. Raw model text never reaches a caller.
  - Every **successful** call returns a usage record with per-user attribution
    and the full token split, so per-audit cost is visible from day one.
    **Daily budgets are measured but not yet enforced** — enforcement is T5.5.
    (Failed calls were originally silent about cost; corrected 2026-08-01 —
    see *Changed* above.)
  - Prompt versions are frozen once published and looked up by exact version;
    there is no "latest", so a re-run reproduces the prompt it originally used
    (D12). The version is returned on every call for recording on the AuditRun.
  - Uploaded documents and chat text are fenced as untrusted data with a
    per-call nonce before entering a prompt.
- **Benchmark knowledge base (T2.3), 2026-07-30.** Five **admin-only**
  endpoints under `/v1/benchmarks` — create, list, read, update, retire. Bands
  are keyed by **sector × stage × metric × region** and carry quartiles
  (`p25`/`p50`/`p75`) plus required `source` and `as_of_date`.
  - **Not visible to founders or investors** — `403`. Publishing the set would
    tell a founder exactly what to claim.
  - `sector` and `region` accept `*` for "any", which is what makes lookup fall
    back from a sector-and-region band to a global one.
  - `metric` enum: `gross_margin_percent`, `runway_months`, `ltv_cac_ratio`,
    `cac_payback_months`, `run_rate_vs_trailing_percent`. Absolute-currency
    figures are absent by design — no FX conversion means amounts are not
    comparable across regions.
  - `higher_is_better` is returned on every band, derived from the metric:
    above `p75` is excellent for gross margin and poor for CAC payback.
  - **Retire, not delete** (`POST /v1/benchmarks/{id}/retire`) — an AuditRun
    cites the benchmark it scored against, so removing a row would strand a
    founder's explanation. Retired bands stay readable and stop matching.
  - `409` on a duplicate key; `422` if quartiles are out of order. Every write
    is recorded in the immutable audit log.
- **Deterministic financial computation (T2.2), 2026-07-30.** `audit/finance.py`
  computes gross margin, net burn, runway, margin-adjusted LTV, LTV/CAC, CAC
  payback, annual run rate, and run-rate-vs-trailing — all in code, never by the
  model (`DECISIONS.md` D9). **No API change yet**: these figures reach clients
  through the audit report in T2.7. Two conventions the mobile app will meet
  when they do surface:
  - **A figure that cannot be computed is `null` with a named reason**
    (`missing_input`, `no_revenue`, `not_burning`, `no_churn`,
    `no_acquisition_cost`, `no_contribution`, `no_trailing_revenue`) — never a
    zero. Render "not known" rather than "0%".
  - **`net_burn` is positive when burning cash**, negative when generating it.
  - Figures stay in the profile's own currency; no conversion is performed.
- **Document upload and download (T1.5), 2026-07-30.** Four endpoints, and
  **the bytes never pass through this API** — they go straight to Cloudflare R2
  on a signed URL, which is why a 25 MB deck does not time out:
  - `POST /v1/startups/{startup_id}/documents` → `201` with a signed
    `upload_url`, `expires_in`, and `max_bytes`. `422` if `content_type` is not
    on the allowlist.
  - `PUT` the file to `upload_url` with the same `Content-Type` you declared
    and **no** `Authorization` header — the signature *is* the credential.
  - `POST /v1/documents/{document_id}/complete` → the server reads the object
    back and judges the **real** size and type. Anything missing, empty, over
    `max_bytes`, or of an unaccepted type is deleted from storage and marked
    `rejected`; `422` carries `details.reason`. Safe to retry.
  - `GET /v1/startups/{startup_id}/documents` → list, newest first.
  - `GET /v1/documents/{document_id}/download` → a short-lived signed URL.
  - **Treat both URLs as bearer credentials** for one object: anyone holding
    one has that access until it expires. Do not log or persist them.
  - New enums the client depends on: `DocumentKind` (`deck` · `financials` ·
    `cap_table` · `other`), `DocumentStatus` (`pending` · `ready` ·
    `rejected`), `ScanStatus` (`pending` · `clean` · `infected` · `skipped`).
  - **No malware scanner is wired yet**, so uploads settle at `skipped` rather
    than being reported `clean` — an unscanned file is not a checked one
    (`TASKS.md` T5.5).

### Changed
- **`R2_ENDPOINT_URL` is now required in production.** `core/storage` cannot
  build a client without it, and a blank endpoint would sign URLs pointing
  nowhere. Startup fails fast instead. *Deployment change only.*
- **Founders must register with a company email address (`DECISIONS.md` D20),
  2026-07-30.** `POST /v1/auth/register` with `role: "founder"` and a consumer
  mailbox (`gmail.com`, `outlook.com`, `yahoo.com`, ...) now returns **`422`**
  with `details = {"field": "email", "reason": "consumer_email_domain"}` —
  branch on `reason` and show it against the email input. Investors are
  unaffected. **This rejection is explicit rather than uniform**, unlike the
  duplicate-address case: it concerns the domain the caller just typed, so it
  reveals nothing about who holds an account. *Client impact: the founder
  signup form needs this error path.*
- **`POST /v1/startups` fills in `name` from the company email domain
  (`DECISIONS.md` D20), 2026-07-30.** Omit `name` and `founder@acme.com`
  yields `Acme`. A `name` you send is never overwritten, and the derived value
  is editable through `PATCH /v1/startups/{id}` like any other field — it is a
  prefill, not a verified company name. When nothing sensible can be read the
  field stays `null` and appears in `missing_fields`. *Additive; no existing
  request breaks.*
- **`POST /v1/startups` is now restricted to founders and admins,
  2026-07-30.** It previously accepted any active account, so an **investor
  could create a startup profile** — `AUTH.md` §5's permission matrix has
  always denied that. Investors now get **`403`**. *No founder client is
  affected.*
- **Tenant isolation consolidated into one check (T1.3), 2026-07-30.** The ownership
  rule that was private to `intake` now lives in `core/ownership.py`, so every
  founder-owned table that follows (documents T1.5, tasks T3.1, evidence T3.5)
  applies the identical decision instead of re-implementing it. Behaviour is
  unchanged and **no API endpoint changed**: another founder's id still returns
  `404` rather than `403`, so the API does not confirm which ids exist.
- **Postgres RLS is deferred to T5.7 (`DECISIONS.md` D19), 2026-07-30.** The deployed
  database role carries `BYPASSRLS`, which makes both `ENABLE` and `FORCE ROW LEVEL
  SECURITY` no-ops — policies written now would enforce nothing while appearing in
  `pg_policies` as though they did. They wait on a least-privilege role provisioned at
  deployment. Until then the app-layer ownership check is the only wall, not merely
  the primary one. No client impact.
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

### Fixed
- **`422` was documented with the wrong schema on two endpoints.** `suspend` and
  `reactivate` omitted `422` from their declared responses, so FastAPI published its
  own `HTTPValidationError` shape instead of this API's error envelope — a client
  coding against the document would have expected the wrong body. Both now declare
  it, `HTTPValidationError` is gone from the document entirely, and
  `tests/unit/test_openapi_contract.py` fails if any endpoint regresses.
- **Every request and response model now publishes an example** (`CLAUDE.md` §6).
  Previously none did. `LoginResponse` publishes **both** branches, so a client can
  see the `mfa_required` shape and not only the happy path.
- **A blank `.env` key no longer takes its trailing comment as its value**
  (`851a7b2`, `6035538`, `781b361`, `2026-07-30`/`31`). **Deployment change
  only — no API change.** Inline-comment stripping is conditional:
  `APP_ENV=development  # ...` parses as `development`, but
  `AI_MODEL_AUDIT=      # strongest model…` parses as *the comment sentence*.
  That turned the audit model id into prose and would have made the first real
  API call a confusing `404`; it hit `CORS_ALLOWED_ORIGINS`, `R2_ENDPOINT_URL`,
  and `STRIPE_WEBHOOK_SECRET` the same way. **No test could see it** —
  `conftest` sets `env_file = None` so a developer's `.env` cannot decide a
  test outcome, which also means the parse never happens during the suite.
  - **First fixed at the wrong depth, corrected 2026-08-01.** `6035538` added a
    lint asserting `.env.example` carries no inline comments — which polices one
    file's formatting in git and leaves the operator's real `.env`, the file
    that actually decides the model id, unguarded. The rule now lives in the
    parse layer: `_blank_to_none` treats any value whose stripped form starts
    with `#` as unset, since no setting can legitimately begin with one.
  - The suite's own `.env` reader in `conftest` had the same hole and was worse
    — it never stripped inline comments at all, so `ANTHROPIC_API_KEY=sk-…  #
    prod key` returned a non-`None` key with the comment attached. That meant
    `requires_anthropic_key` would **not** skip, and the live tests would fail
    as a `401` that reads like a revoked key rather than a parse bug.

### Added
- **Startup Profile** (T1.4) — the first founder-owned resource.
  - `POST /v1/startups` — create your own profile. **Every field is optional**: a
    founder can start with a name and fill the rest in later, or let extraction do
    it. `owner_id` comes from the token and is not an accepted request field.
    `409` if you already have one (one per founder in v1).
  - `GET /v1/startups/me` — your own profile, without needing its id.
  - `GET /v1/startups/{id}` and `PATCH /v1/startups/{id}` — **another founder's id
    returns `404`, not `403`**, so the API never confirms which ids exist. SACI
    admins can read any profile; investors cannot (they get summaries in T4.2).
  - `PATCH` is partial and **merges `fields` by name**, so correcting one value
    does not resend the document and extraction does not overwrite typed input.
  - Each field carries `source` (`founder` | `document` | `inferred`),
    `confidence`, and an optional `document_id` — provenance is part of the value,
    not a parallel structure, because the audit must cite its evidence.
  - `missing_fields` is **computed on read**, not stored: it depends on the field
    set and rubric version, so a stored copy would go stale.
  - **`sector` is free text, not an enum** (`DECISIONS.md` D11 — the platform must
    accept sectors that do not exist yet). `stage`, `country` (ISO 3166-1 alpha-2)
    and `currency` (ISO 4217) are indexed for benchmarks and discovery.
  - The field list is **provisional** pending `saci-audit-platform-backend-spec.md`,
    which is not in the repo. JSONB storage means changing it needs no migration.
- Repository scaffold: module/layer structure per `ARCHITECTURE.md`, `pyproject.toml`,
  `.env.example`, README (T0.1). No API endpoints yet.
- Tooling and CI (T0.2): ruff (lint + format), mypy in strict mode, pytest, and a
  gitleaks secret scan, all wired into a GitHub Actions workflow. No API change.
  - **Correction, 2026-07-31: this originally claimed the workflow "runs on
    every push and pull request". It did not — it had never run at all.** The
    file sat at `backend/.github/workflows/ci.yml`, but GitHub Actions only
    discovers workflows under `/.github/workflows` at the **repository** root,
    which since `37344d3` is the monorepo root rather than `backend/`. Every
    push between T0.2 and 2026-07-31 was unchecked, and the entry above read as
    protection the whole time. Fixed in `74cc8d7` by moving the workflow to the
    root with `defaults.run.working-directory: backend`; first observed green
    run recorded in `87f60b5`. See `TASKS.md` open follow-ups for what a green
    badge does and does not cover — db-backed tests still skip on the runner.
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
- **Admin user management** (T1.2d) — all four routes require an admin **with MFA
  enrolled**, so none of this is reachable without a second factor.
  - `POST /v1/admin/users` — provision an admin. The only path that creates one;
    `/v1/auth/register` refuses the role. The new admin lands
    `pending_verification` without MFA, so it confers no power until both are
    done. A duplicate address returns `409` (unlike registration, the caller is
    already trusted, so there is no enumeration concern).
  - `POST /v1/admin/users/{id}/suspend` — blocks the account and **ends its
    sessions immediately**. `403` on your own account, `409` if it is the only
    active admin.
  - `POST /v1/admin/users/{id}/reactivate` — returns to `active`, or to
    `pending_verification` if the address was never verified.
  - `PATCH /v1/admin/users/{id}/role` — **forces the user to log in again** so the
    new role applies at once. `403` on your own account, `409` if it would leave
    no active admin.
  - The first admin is created by `scripts/create_admin.py` (needs database
    credentials); there is no bootstrap endpoint.
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
