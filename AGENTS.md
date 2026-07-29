# AGENTS.md — FundReady Backend

Standing rules for every coding session, the stack, the exact commands, and conventions. Read this together with `CLAUDE.md` (rules), `ARCHITECTURE.md` (structure), `DECISIONS.md` (rationale), and `TASKS.md` (the queue).

---

## 1. Session protocol (every time)

1. Read `CLAUDE.md`, skim `ARCHITECTURE.md` and `DECISIONS.md`.
2. Open `TASKS.md` and take the **next unchecked task** — one task only.
3. Restate the task and propose a short plan. Wait for confirmation on anything non-trivial.
4. Implement within the layer boundaries. Small, focused changes.
5. Add/adjust tests — security-critical paths first.
6. Run lint, type-check, and tests. Everything green.
7. Update API docs, `CHANGELOG`, migrations, and `.env.example` if the change requires them.
8. Mark the task done in `TASKS.md` and make one clear commit.

Do not skip ahead in `TASKS.md`. Do not "improve" decisions recorded in `DECISIONS.md` without raising it first.

## 2. Stack

- **Language/framework:** Python + FastAPI
- **DB / auth / storage / vectors:** Supabase (Postgres, Auth, Storage, pgvector)
- **Migrations:** Alembic
- **Background jobs:** Redis + worker (RQ/Celery)
- **AI:** Claude API (via `app/ai/`)
- **Payments/KYC:** Stripe (Billing, Checkout, Identity)
- **Email:** Resend (or SES)
- **Test / lint / types:** pytest · ruff · mypy

> These are the working defaults from the PRD. Changing a stack element is a `DECISIONS.md`-level change — raise it first.

## 3. Commands

Treat these as the canonical project commands. Keep them accurate if tooling changes.

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # or: uv sync
cp .env.example .env                      # then fill in secrets

# Run
uvicorn app.main:app --reload            # API (dev)
python -m app.workers.queue              # background worker

# Database
alembic revision --autogenerate -m "msg" # create a migration
alembic upgrade head                     # apply migrations

# Quality
pytest                                   # all tests
pytest tests/security                    # security-critical tests
pytest tests/path::test_name             # one test
ruff check . && ruff format .            # lint + format
mypy app                                 # type-check

# API docs
# OpenAPI is served at /docs and /openapi.json when the app runs.
```

## 4. Conventions

- **Types everywhere.** Pydantic for all request/response bodies; reject unknown fields. `mypy` must pass.
- **Enums are enums.** Roles, audit status, task type/status, evidence result, report tier, interest/meeting state are typed enums shared with schemas — never magic strings.
- **Formats:** timestamps ISO 8601 in UTC; currency as ISO 4217 codes; money as integer minor units. Apply everywhere.
- **Errors:** raise typed exceptions; the global handler returns `{ "error": { "code", "message", "details" } }`. Never leak stack traces.
- **API:** REST under `/v1`; plural resource nouns; correct status codes; additive changes preferred; breaking changes need a new version + `CHANGELOG` entry.
- **Auth:** identity comes from the verified token only. Every endpoint authorizes and checks ownership. Never trust client-supplied role/tier/ids.
- **Secrets:** env/secret-manager only. Never in code, logs, or git. Keep `.env.example` complete but valueless.
- **DB:** schema changes only via Alembic. Repositories hold queries; services hold logic.
- **AI:** all model calls via `app/ai/client.py`; structured JSON output validated before use; prompts and rubrics are versioned; financial numbers computed in `finance.py`, not by the model.
- **Commits:** small and scoped. Message format: `<module>: <what changed>` (e.g. `audit: add consistency-check stage`).
- **Branches:** `feat/<task-id>-short-name`, `fix/…`.
- **Tests:** write security-path tests first (authz, tenant isolation, tier filtering, gating, webhooks).

## 5. Definition of done (per task)

- Behavior matches the task's acceptance notes and the PRD/spec.
- Layer boundaries respected (router→service→repository).
- Tier filtering and authorization enforced server-side where relevant.
- Tests added and passing; lint + types clean.
- API docs / `CHANGELOG` / migrations / `.env.example` updated as needed.
- Task checked off in `TASKS.md`; one clear commit.

## 6. Guardrails

The security, data-tier, and AI rules in `CLAUDE.md` §4–§5 are non-negotiable and override convenience. If a task seems to require breaking one, stop and ask.
