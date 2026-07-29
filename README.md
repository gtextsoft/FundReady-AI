# FundReady — Backend & AI

Backend and AI service for **FundReady**, SACI Holdings' two-sided, SACI-brokered
audit and investor-matching platform.

Founders submit their business and receive a fully automated AI audit of whether it
is **fundable** and **saleable**, plus report-driven tasks they must complete and
prove with uploaded evidence to become investor-visible. Investors discover startups
as **summaries**, chat with an AI analyst, and book meetings. **SACI is the broker**
and the only party that reveals a full report.

> **Scope:** backend + AI only. The mobile client is built separately by another
> developer, so the documented API contract is the deliverable
> (`DECISIONS.md` D1). Do not build frontend/UI in this repo.

## Stack

| Layer | Choice |
|---|---|
| Language / framework | Python + FastAPI |
| Database, auth, storage, vectors | Supabase (Postgres, Auth, Storage, pgvector) |
| Migrations | Alembic |
| Background jobs | Redis + RQ worker |
| AI | Claude API, via `app/ai/` |
| Payments / KYC | Stripe (Billing, Checkout, Identity) |
| Email | Resend |
| Test / lint / types | pytest · ruff · mypy |

## Getting started

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env                                 # then fill in secrets
```

`pyproject.toml` is the single dependency manifest — there is no
`requirements.txt`.

## Commands

```bash
# Run
uvicorn app.main:app --reload            # API (dev)
python -m app.workers.queue              # background worker

# Database
alembic revision --autogenerate -m "msg" # create a migration
alembic upgrade head                     # apply migrations

# Quality
pytest                                   # all tests
pytest tests/security                    # security-critical tests
ruff check . && ruff format .            # lint + format
mypy app                                 # type-check
```

## API documentation

The OpenAPI document is the source of truth for the mobile developer. With the app
running:

- Swagger UI — `/docs`
- ReDoc — `/redoc`
- OpenAPI JSON — `/openapi.json`

All resources live under `/v1`. Timestamps are ISO 8601 UTC, currencies are ISO 4217
codes, and money is expressed in integer minor units. Errors always use the envelope
`{"error": {"code", "message", "details"}}`.

## Layout

```
app/
├── main.py       FastAPI app; mounts the /v1 routers
├── core/         config, db, security, errors, logging, deps
├── modules/      identity · intake · audit · readiness · commerce ·
│                 investor · brokerage · recommendation · notifications
├── ai/           the only place that calls the Claude API
└── workers/      idempotent background jobs
migrations/       Alembic — the only way the schema changes
tests/            unit · integration · security
```

Request path is strictly **router → service → repository**. See `ARCHITECTURE.md`.

## Non-negotiables

- **Report tiers are enforced server-side.** Investors see summaries only;
  founders see their own audit only; SACI admins see everything. Only an
  audit-logged SACI admin action reveals a full report (`DECISIONS.md` D8).
- **Financial figures are computed in code**, in `app/modules/audit/finance.py` —
  never by the LLM (`DECISIONS.md` D9).
- **Identity comes from the verified token only.** Client-supplied role, tier,
  or ids are never trusted; ownership is checked on every object access.
- **Secrets live in the environment**, never in code, logs, or git.

## Documentation

| File | What it covers |
|---|---|
| `CLAUDE.md` | Session rules and security/AI guardrails — read first |
| `AGENTS.md` | Stack, commands, conventions, definition of done |
| `ARCHITECTURE.md` | Folder structure, layer boundaries, where files go |
| `DECISIONS.md` | Decisions that must not be silently reversed |
| `AUTH.md` | Authentication and authorization design |
| `TASKS.md` | The build queue — one task at a time |
| `fundready-prd.md` | Product requirements |
| `CHANGELOG.md` | API-affecting changes |
