# Where the project is — 2026-08-04, end of session

Snapshot for picking this up cold. Submission target is **2026-08-05**.
Everything below was verified in this session unless marked otherwise.

---

## The spine works end to end

Register → verify email → log in → profile → audit → report → publish →
discover → express interest → SACI approves → SACI reveals → investor reads.

**Every step has been exercised against live infrastructure**, except the
deploy. Three things went from "never run" to "proven" today:

| | Proven | Notes |
|---|---|---|
| **Audit queue** | 2026-08-03 | Upstash Redis, real worker, run `b8eabf62` reached `succeeded` |
| **Live model call** | 2026-08-03 | `claude-opus-5`. Fundability `provisional` 50, saleability 46, integrity 100, 44 action items |
| **Document storage** | 2026-08-04 | R2 round trip: PUT → HEAD → signed GET → DELETE, bytes matched |
| **Transactional email** | 2026-08-04 | Resend, `delivered` to a real inbox |

## Test and gate state

- Unit: **574 passed**
- Security (DB-backed), this session: report tiers 16, report access 12,
  discovery 12, reveal gate 11
- `ruff check` · `ruff format --check` · `mypy app` — **all clean**
- OpenAPI: **39 paths, 44 operations**, exported to `docs/openapi.json`
- Migrations: head is `0011_brokerage`, applied to Neon and **proven down and
  back up**

## Task status

| Phase | State |
|---|---|
| 0, 1 | Complete except **T1.2a** (email now works — the task line still says otherwise, worth closing) |
| 2 | 8 of 10. Open: **T2.4a** (extraction not wired into the pipeline), **T2.9** (billed accuracy half unbuilt) |
| 3 | **Not started.** Readiness tasks, evidence, Stripe — all empty stubs |
| 4 | T4.2 ✅ · T4.6 ✅ · T4.3 `[~]` · T4.5 `[~]` · T4.1, T4.4 not started |
| 5 | Not started |

---

## Do these next, in this order

1. **Deploy to Render.** `render.yaml` is at the repo root and verified against
   the code; `backend/docs/DEPLOY.md` is the runbook and was checked line by
   line. Start as `APP_ENV=staging` — `production` refuses to boot without
   Stripe and R2 settings that partly do not exist yet. Estimated 1–2 hours.
2. **Seed benchmark data.** The table is empty, so the rubric is told to lower
   its confidence on every dimension, which is why the live run came back
   `provisional` rather than `ready`. Content work, not engineering.
3. **Cap the action plan.** The real run produced **44 items**. They are good
   and specific, but no founder reads 44. Group by dimension or take the top N.

## Credentials to rotate — all three are in a chat transcript

Not committed (`.env` is gitignored, no history), but treat as public:

- Upstash REST token — currently also serves as the Redis password
- Cloudflare account API token (`cfat_…`)
- Resend API key

The R2 S3 keys in `.env` were minted *by* the Cloudflare token but are
independent of it, so rolling it breaks nothing that is running.

## Known gaps that will bite

- **`APP_LINK_BASE_URL` is a placeholder** (`https://stephenakintayofoundation.org/app`).
  Verification emails point there; it should be the mobile deep link, and only
  the mobile developer can supply the scheme.
- **Mobile registration still returns `422`** — the client does not send
  `first_name`/`last_name`. One-line fix in their tree.
- **The four market/growth questions are not in the mobile form.** Until they
  are, no founder can reach a `ready` verdict.
- **A run stranded in `running` polls forever.** No lease; documented in
  TASKS.md open follow-ups.
- **Tests run against the production database** — safe only while fixtures roll
  back. Provision a second Neon branch before real users exist.
- **No rate limiting** on a public, expensive AI endpoint.

## The one honest caveat on quality

The audit pipeline is **proven but unmeasured**. The golden set exists and is
scored, but six of its eight companies were scored by Claude, so an accuracy
run over them partly measures a model agreeing with itself — `reviewed_by`
keeps that visible. And the live run scored **50** on a profile the golden set
predicts at **72–92**, so either the hand-scoring is optimistic or empty
benchmarks suppress scores. Resolving that is what item 2 above buys.

## Documents worth reading first

| File | What it is |
|---|---|
| `AI-READINESS.md` | Status report written for a non-engineer audience |
| `PLAN-WEDNESDAY.md` | The ship plan, with a cut line by clock time |
| `FOUNDER-ONBOARDING.md` | Every question asked, plus 17 criteria still unserved |
| `CLIENTS.md` | The mobile developer's contract — §5b report, §5c discovery, §5d brokerage |
| `docs/DEPLOY.md` | Render runbook, verified against the code |
| `TASKS.md` | Source of truth for what is done and why |
