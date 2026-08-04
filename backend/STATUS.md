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

- Unit: **611 passed**
- Security (DB-backed), this session: report tiers 16, report access 12,
  discovery 12, reveal gate 11
- `ruff check` · `ruff format --check` · `mypy app` — **all clean**
- OpenAPI: **39 paths, 44 operations**, exported to `docs/openapi.json`
- Migrations: head is `0011_brokerage`, applied to Neon and **proven down and
  back up**

## Task status

| Phase | State |
|---|---|
| 0, 1 | Complete |
| 2 | 9 of 10 built. **T2.4a** wired 2026-08-04 (documents now reach the audit) but no document has run through end to end. **T2.9** billed accuracy half still unbuilt |
| 3 | **Not started.** Readiness tasks, evidence, Stripe — all empty stubs |
| 4 | T4.2 ✅ · T4.6 ✅ · T4.3 `[~]` · T4.5 `[~]` · T4.1, T4.4 not started |
| 5 | T5.7 in progress (Render) · rest not started |

### Landed 2026-08-04, after the snapshot above was first written

- **`render.yaml` was moved into `backend/` by `a2e53d6` and moved back.** Render
  reads a Blueprint only from the repository root, so as pushed the deploy config
  was invisible. Same failure as the CI workflow that sat under `backend/`.
- **Dependency versions are pinned** by `backend/constraints.txt`, used by both
  Render build commands and the CI install step. `anthropic` is the pin that
  earns it: `ai/client.py` is written against one request shape and a break
  there is silent, expensive, and invisible to CI.
- **`python -m app` binds `0.0.0.0` on Render**, keyed off the `RENDER` variable.
  It defaulted to loopback, which fails Render's port scan with an error that
  says nothing about the host.
- **T2.4a** — documents reach the audit. Extracted fields are merged *in memory*
  and deliberately not written back to the profile; see TASKS.md for why that
  would double-bill.
- **One lease closes three audit-run bugs** — the redelivery double-bill, the run
  stranded in `running`, and its `queued` sibling.
- **The rubric's declared weights are applied**, and the 44-item action plan now
  carries `is_priority` (at most five, one per dimension, nothing truncated).

---

## Do these next, in this order

1. **Finish the Render deploy.** Two services from `backend/`: a **Web Service**
   running `python -m app` and a **Background Worker** running
   `python -m app.workers.queue`. The worker in a Web Service is what the first
   attempt got wrong — it opens no port, so Render's scan times out and kills a
   process that was working. Set `APP_ENV=staging` and
   `MFA_SECRET_ENCRYPTION_KEY`; without the latter no admin can enrol MFA and
   `require_role(ADMIN)` then refuses everything, which blocks item 2.
2. **Seed benchmark data.** The table is empty, so the rubric is told to lower
   its confidence on every dimension, which is why the live run came back
   `provisional` rather than `ready`. Content work, not engineering — but it
   needs a working admin, hence the ordering.
3. **Run one audit with a real deck + financials through the deployed worker.**
   That is the only thing left that closes T2.4a, and it is the first time any
   document will have been read end to end.

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
- **Document bytes are capped per object, not in aggregate.** `_score` pulls
  every auditable document into the worker before the model calls: 25 MiB each,
  unbounded total. Ten uploads is 250 MiB on a Starter instance, and an
  OOM-killed worker strands a run — the failure the lease now repairs, half an
  hour later. Fine for one founder with one deck; fix before real volume.
- **The golden-set bands were never re-derived after weighting.** They are
  checked for reachability, not against computed scores, so the suite stayed
  green through the weight change. Re-derive them when T2.9 Layer B runs.
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
