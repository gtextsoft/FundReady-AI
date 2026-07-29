# ARCHITECTURE.md — FundReady Backend

How the code is organized, where files go, and how data flows. If a change would break a layer boundary or put a file in the wrong place, stop and reconsider.

---

## 1. Shape

A **modular monolith**: one deployable FastAPI service, split into independent feature modules with strict internal boundaries. Long-running work (audits, evidence assessment) runs on a background worker off the request thread. We can split modules into separate services later without rewriting them — that's the point of the boundaries.

## 2. Folder structure

```
fundready-backend/
├── app/
│   ├── main.py                 # FastAPI app, mounts /v1 routers, wires middleware/handlers
│   ├── core/                   # cross-cutting concerns (no business logic)
│   │   ├── config.py           # env-driven settings
│   │   ├── db.py               # engine, session, base
│   │   ├── security.py         # token verification, current_user, RBAC deps
│   │   ├── errors.py           # error envelope + exception handlers
│   │   ├── logging.py
│   │   └── deps.py             # shared FastAPI dependencies
│   ├── modules/                # one folder per feature module
│   │   ├── identity/
│   │   │   ├── router.py       # HTTP endpoints only
│   │   │   ├── service.py      # business logic + authorization
│   │   │   ├── repository.py   # DB access only
│   │   │   ├── schemas.py      # Pydantic request/response (incl. per-tier response schemas)
│   │   │   └── models.py       # ORM tables
│   │   ├── intake/
│   │   ├── audit/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── schemas.py
│   │   │   ├── models.py
│   │   │   ├── pipeline.py     # orchestrates the audit stages
│   │   │   ├── finance.py      # DETERMINISTIC financial computation (no LLM)
│   │   │   └── rubric/         # versioned rubric definitions (v1, v2, …)
│   │   ├── readiness/          # tasks, evidence, gating, re-audit
│   │   ├── commerce/           # Stripe: catalogue, checkout, subscriptions, webhooks
│   │   ├── investor/           # profiles, discovery, ranking, investor AI chat
│   │   ├── brokerage/          # interest, SACI approval, meetings, report reveal
│   │   ├── recommendation/     # gap→program matching, per-country
│   │   └── notifications/      # transactional email
│   ├── ai/                     # SHARED AI orchestration (used by modules via services)
│   │   ├── client.py           # Claude API wrapper, model tiering
│   │   ├── prompts/            # versioned prompt templates
│   │   ├── schemas.py          # structured-output JSON schemas
│   │   ├── guards.py           # injection defense, output validation, tier-scoped retrieval
│   │   └── caching.py          # prompt caching helpers
│   └── workers/                # background jobs
│       ├── queue.py            # queue setup (Redis)
│       └── tasks.py            # idempotent job handlers (run_audit, assess_evidence, …)
├── migrations/                 # Alembic migrations (the ONLY way schema changes)
├── tests/
│   ├── unit/
│   ├── integration/
│   └── security/               # authz, tenant isolation, report-tier, gating, webhooks
├── scripts/
├── .env.example
├── pyproject.toml
├── alembic.ini
├── README.md
├── CLAUDE.md                   # session rules (read first)
├── AGENTS.md                   # commands + conventions
├── ARCHITECTURE.md             # this file
├── DECISIONS.md                # why things are the way they are (don't silently change)
└── TASKS.md                    # the work queue (one task at a time)
```

## 3. Layer boundaries (strict)

Request path is **router → service → repository**. Never skip or cross layers.

- **router** — HTTP only. Validate input with `schemas`, call one service method, return a response schema. **No business logic, no DB access, no LLM calls.**
- **service** — business logic and orchestration. Performs **authorization/ownership checks**, calls `repository`, `ai`, and other modules' services through their public service interface (never their internals). Enqueues background jobs.
- **repository** — database access only. Queries in, models/data out. **No business rules.**
- **schemas** — Pydantic request/response models, including the **per-tier response serializers** (summary vs full). Tier filtering happens here, driven by the service.
- **models** — ORM table definitions.
- **ai/** — the only place that talks to the Claude API. Modules reach it via their service, never directly from routers.
- **workers/** — long-running, idempotent jobs. Services enqueue; workers execute the `pipeline`.
- **core/** — config, db, security, errors, logging, shared deps. No feature logic.

Modules do not import each other's `repository`, `models`, or internals — only each other's `service` public functions.

## 4. Data flow

**Synchronous request:**
`client → router (validate) → service (authz + logic) → repository (DB) / ai / other services → response schema (TIER-FILTERED) → client`

**Audit (asynchronous):**
1. Founder submits via `intake` → profile persisted.
2. `audit.service` enqueues a `run_audit` job (idempotent).
3. Worker runs `audit/pipeline.py`: extraction → consistency check → `finance.py` (code) → rubric scoring (`ai`, structured output) → synthesis → persist `AuditRun` + embeddings.
4. `notifications` emails the founder; the mobile app reads status/result via the `audit` router.

**Readiness loop:**
`audit generates tasks → founder completes + uploads evidence → assess_evidence job (ai, per-task criteria) → pass → re-audit affected dimensions → gate re-evaluates investor-visibility`.

## 5. Where files go (quick rules)

| You are adding… | Put it in… |
|---|---|
| A new endpoint | `modules/<module>/router.py` (+ schema, + a service method) |
| Business logic | `modules/<module>/service.py` |
| A DB query | `modules/<module>/repository.py` |
| A DB table | `modules/<module>/models.py` **and** a new Alembic migration |
| A request/response shape or tier serializer | `modules/<module>/schemas.py` |
| A prompt or its new version | `ai/prompts/` (versioned) |
| A structured-output schema | `ai/schemas.py` |
| A financial calculation | `modules/audit/finance.py` (never in a prompt) |
| A rubric change | `modules/audit/rubric/` as a **new version** |
| A long-running job | `workers/tasks.py` (+ service enqueues it) |
| Auth / config / error handling | `core/` |
| A security-sensitive behavior test | `tests/security/` |

## 6. Non-negotiable placements

- **Financial math** lives in `audit/finance.py` — code, not the LLM.
- **Tier filtering** lives in `schemas.py` serializers, enforced by services — never left to the client.
- **All Claude calls** go through `ai/client.py`.
- **All schema changes** go through `migrations/` — never hand-edit the DB.
