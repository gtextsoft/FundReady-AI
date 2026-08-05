# Pre-push notes — the readiness loop (T3.1 + T3.5 + T3.6)

**Session:** 2026-08-05 · **Branch:** `main`

Three tasks landed, and together they close Phase 3's readiness loop:

| | |
|---|---|
| **T3.1** | An audit's action plan becomes durable, trackable tasks |
| **T3.5** | A founder proves a task with evidence, and the AI grades it |
| **T3.6** | The gate: no required task outstanding, no investor sees you |

An audit now generates tasks, evidence is graded against them, and discovery
refuses a startup that has not done the work. That was the product's central
claim and it was not being delivered.

> Commit `b1a5795` landed mid-session outside my control. Check `git log` before
> writing your own commit message.

---

## Why this work

The audit engine was finished and proven, and it was producing **44 action items
per run** — which it serialised into `AuditRun.report` (a JSONB column) and
stopped. Nothing durable, nothing trackable, nothing a founder could work
through, and nothing that changed who investors could see.

`app/modules/readiness/` was five files containing docstrings and nothing else.

---

## What shipped

**The gate (T3.6) adds no endpoint.** It changes what `GET /v1/discover` and
`GET /v1/discover/{id}` return, and extends the task summary. That is the point:
the wall sits inside a query that already exists rather than a new route somebody
could forget to call.

**Tasks (T3.1)**

| Endpoint | Purpose |
|---|---|
| `GET /v1/startups/{id}/tasks` | The list. Paged, filterable by `status` and `requirement` |
| `GET /v1/startups/{id}/tasks/summary` | Counts and gate state, for a home screen |
| `GET /v1/startups/{id}/tasks/{task_id}` | One task |

**Evidence (T3.5)**

| Endpoint | Purpose |
|---|---|
| `POST /v1/tasks/{id}/evidence` | Reserve an upload, get a signed URL |
| `POST /v1/evidence/{id}/complete` | Confirm the file; queues grading |
| `GET /v1/tasks/{id}/evidence` | Submissions for a task, newest first |
| `GET /v1/evidence/{id}/download` | Expiring signed URL |
| `POST /v1/admin/tasks/{id}/reopen` | **Admin.** Clear the attempt cap; audit-logged |

OpenAPI went **39 paths / 44 operations → 46 / 52**.

New enums: `Requirement`, `TaskStatus`, `Dimension`, `EvidenceStatus`,
`AssessmentOutcome`. New task fields: `assessment_attempts`,
`attempts_remaining`. New summary fields: `has_audit`, `gate_cleared`,
`investor_visible`.

### Files

**New**

- `app/modules/readiness/generation.py` — pure: task generation and classification
- `app/modules/readiness/evidence.py` — pure: upload lifecycle, outcomes, the attempt cap
- `app/modules/readiness/assessment.py` — the grading prompt and model call
- `migrations/versions/…-0012_readiness_tasks_….py`
- `migrations/versions/…-0013_evidence_….py`
- `tests/unit/test_readiness_generation.py` — 23 tests
- `tests/unit/test_evidence_assessment.py` — 15 tests
- `tests/security/test_readiness_tasks.py` — 20 DB-backed tests
- `tests/security/test_evidence.py` — 22 DB-backed tests
- `tests/security/test_readiness_gate.py` — 18 DB-backed tests

**Modified**

- `app/modules/readiness/{models,repository,schemas,service,router}.py` — were docstring stubs
- `app/modules/investor/repository.py` — the gate, in `_visible`
- `app/modules/audit/service.py` — passed evidence joins the fingerprint
- `app/modules/audit/repository.py` — `latest_succeeded`
- `app/workers/tasks.py` — task generation after the report commits; the `assess_evidence` job
- `app/workers/queue.py` — `enqueue_assessment` and its timeout
- `app/modules/identity/models.py` — `AuditAction.TASK_REOPENED`
- `app/modules/audit/extraction.py` — `document_blocks` promoted from private
- `app/modules/intake/service.py` — `safe_filename` promoted from private
- `app/main.py` — router mounted
- `tests/integration/test_audit_worker.py` — 9 wiring tests added
- `tests/unit/test_worker_queue.py` — 3 tests, incl. the job-id validator
- `docs/openapi.json` — re-exported
- `CLIENTS.md`, `CHANGELOG.md`, `TASKS.md`, `STATUS.md`

**Two helpers were promoted from private rather than copied.** Evidence is the
same problem as a deck — a PDF or photograph must go to the API as a native
block, and a founder's filename must be reduced the same way — and a second copy
is a second place to forget a rule.

---

## T3.1 — task generation

**`required` vs `recommended` is computed, not judged.** PRD §4.2 says blocking
gaps become required tasks, so "blocking" has to mean something arithmetic. It
means exactly what `synthesis._verdict_for` means: a dimension that could not be
scored (trips the `thin` rule) or scored below `READY_THRESHOLD`. The constant is
**imported, not restated**, so it cannot drift.

**A re-audit reconciles; it never rewrites.** Every audit produces a *complete*
action plan. The obvious implementation — delete this startup's tasks, insert the
new plan — throws away the founder's progress each time they re-audit, and **the
test suite stays green** because each individual row looks correct.
`uq_readiness_tasks_action` on `(startup_id, action_fingerprint)` makes the
second audit *find* the existing row.

**Only an untouched task can be retired.** A gap the new audit stops raising goes
`obsolete` — but solely from `open`. Anything carrying evidence keeps its state
and history. A retired gap that comes back **reopens**, so a regression is
visible rather than silently absent.

**No endpoint completes a task, and there will not be one.** `DECISIONS.md` D10:
readiness is earned. There is no request schema carrying a status, and that
*absence* is the enforcement.

---

## T3.5 — evidence and grading

**The criterion is the task's `action`, unmodified.** T2.6 writes every
`unmet_criteria` entry as a *completable action* specifically so something
downstream can grade against it. The founder can never fail against a hidden
standard, and there is no paraphrase step to drift.

**Ambiguity resolves to `needs_more`** — never a pass, never a fail. `CLAUDE.md`
§5's thin-data guarantee one layer below the audit. Both error directions are
expensive: a false pass admits an unready startup, a false fail burns one of
three attempts.

**Three graded attempts per task, then it locks.** *Your call, asked rather than
guessed* — it was an open question in `TASKS.md`. A cap has to exist and that
part is not a preference: grading is a model call, a model does not answer
identically twice, so unlimited attempts means a determined founder eventually
passes anything — at a billed `AUDIT`-tier call each time, with no per-user
budget behind it yet (T5.5). **Three is untuned.**

**Locking is not failing.** At the cap the task keeps its last status and the
*upload* is refused. A `fail` is a statement about the work; a lock is a
statement about the process.

**The counter increments on the grading, not the upload.** Three files attached
to one task is one attempt — the grader reads a task's outstanding submissions as
one set.

**Reopening is admin-only and audit-logged.** A counter the counted party can
reset is not a cap. A `passed` task is reopenable too, deliberately — that is the
dispute path, so T3.6 did not need a second one.

**The grader cannot write a task status.** `AssessmentOutcome` and `TaskStatus`
are separate vocabularies joined by an explicit mapping. The mapping's **range**
is asserted, not just its keys: no outcome can write `obsolete` or `open`.

---

## T3.6 — the gate

Three conditions, all in SQL, all inside `investor.DiscoveryRepository._visible`:
opted in, **and** a succeeded audit, **and** no required task outstanding.

**Enforced at the read, not at `publish`.** Consent and eligibility go stale on
different schedules. A founder who was eligible when they published stops being
eligible the moment a re-audit raises a new required gap — and a check written at
publish time would leave them discoverable anyway. `intake.set_discoverability`
is unchanged and still always succeeds; its own docstring predicted T3.6 would
"constrain the publish branch only", and that turned out to be the wrong call.

**In SQL for the reason that module already gives:** a filter applied after the
fact is one forgotten call away from publishing every founder on the platform.
There is no unfiltered variant of the query to reach for by mistake. The live
check confirmed `/discover/{id}` is covered too, not just the list.

**Outstanding is scoped to the tasks the *latest* run raised** — the call that
matters, and a naive predicate gets it wrong. `_retire_unraised` retires only
`OPEN` rows (deliberately, so evidence is never erased), so a task graded
`failed` keeps that status forever, even after a later audit stops raising the
gap. Counting it would leave that founder **permanently invisible with no
self-service path**: the gap is absent from the current report so no new evidence
can address it, and an admin reopen sets it to `open`, which is still not
`passed`. Scoping to `audit_run_id == latest.id` makes the gate mean "outstanding
according to the report an investor would actually be shown".

**Passed evidence joins the audit's inputs, and that is the whole re-audit.**
`input_fingerprint` hashes the document keys, so a founder who worked through
their plan has changed what the audit reasons over — the hash moves and the
existing `POST /v1/startups/{id}/audits` mints a genuinely new run instead of
handing back the pre-work verdict. Evidence is selected by joining to the task
rather than by `Evidence.outcome`, so a task reopened and re-graded stops feeding
the audit a grading that was overturned.

**No automatic re-audit on a pass**, deliberately. It would put a billed job
dispatch inside the grading transaction — the failure this codebase has already
hit twice — and the trigger condition is computed from rows that same transaction
just wrote, so a redelivery could fire it twice. ⚠️ **The consequence is real: a
founder who finishes their tasks is not visible until they request a re-audit.**
Prompt them in the client.

**`ReadinessSummary` reports eligibility and consent separately** (`gate_cleared`
vs `investor_visible`). They fail for different reasons and are fixed by
different actions, so collapsing them would leave a founder unable to tell "you
have work left" from "you have not opted in".

---

## Three bugs caught before shipping — none by a passing test

### 1. Task generation could re-bill an audit and lose the report

Generation was first written into the same transaction as `mark_succeeded`. That
block sits **outside** the `try` covering the model calls, so a raise there
propagated out of `run_audit_async` onto RQ's failed queue for an automatic
retry — and every retry re-enters at the top for another billed `claude-opus-5`
high-effort pass. Sharing the transaction made it worse: the rollback discarded a
report already paid for and stranded the run in `running`. That is the exact
three-bug cluster commit `8743273` closed, through a new door.

Verified before fixing by raising from `generate_for_report` and watching the
exception escape. The report now commits on its own; generation is best-effort in
its own transaction.

### 2. The RQ job id used a colon

`enqueue_assessment` built `assess:{task_id}`. **RQ validates job ids against
letters, numbers, underscores and dashes** and raises on anything else — so
completing an evidence upload returned a **`500`**, *after* the founder's file
had reached the bucket and the task had been marked `submitted`.

655 unit tests, 339 security tests and clean `mypy` all passed with this in
place. Every test that touches a dispatch path patches `enqueue_assessment` out,
because Redis is not what those tests are about. Only a real dispatch reaches the
validator. `test_every_job_id_passes_rqs_own_validator` now asserts both shapes
against **RQ's own `validate_job_id`** rather than a restated regex.

### 3. The attempt cap was bypassable

`MAX_ASSESSMENT_ATTEMPTS` was checked **only when an upload was reserved**.
Reservations are cheap and unmetered, so: take ten tickets while the counter
reads zero, cash them one at a time afterwards, walk past the ceiling. Every
existing cap test passed because they all reserve *after* setting the cap.

Now re-checked at `complete` (before the storage call) and again in the worker
before spending. **The state that matters is the state at the moment work is
dispatched** — a limit checked where work is *requested* rather than where it is
*performed* is not a limit.

### Bonus: the tiebreaker bug the T3.6 tests found

Three of the new gate tests failed on first run, and the cause was not the gate.
**Postgres `now()` is the *transaction* timestamp**, so two audit runs written in
one transaction share `created_at` to the microsecond. Neither the discovery
query's `DISTINCT ON ... ORDER BY created_at DESC` nor `latest_succeeded` had a
tiebreaker — so with a tie they could resolve to **different runs**, and the
founder's summary would say "cleared" while discovery hid them.

Both now order by `created_at DESC, id DESC`, and both say in a comment that they
must stay in step.

---

## How it was verified

| Check | Result |
|---|---|
| Unit | **655 passed** |
| `ruff check` · `ruff format --check` · `mypy app` | clean |
| Migrations `0012` and `0013` | applied to Neon, each proven **down and back up** |
| Live HTTP — T3.1 | **19/19 checks** |
| Live HTTP — T3.5, incl. a real R2 round trip | **17/17 checks** |
| Live HTTP — T3.6 gate | **11/11 checks** |
| Security + integration | **confirm before pushing** — see the checklist |

**The live-server passes earned their keep three times.** They caught the route
ordering trap (`/tasks/summary` must be declared before `/tasks/{task_id}`), the
RQ job-id `500`, and confirmed `/discover/{id}` is gated as well as the list.

**Five mutations proved the key tests can actually fail** — a green test that
cannot go red proves nothing:

1. Removed the worker's generation call → wiring test red.
2. Removed the `startup_id` filter from the retirement query → cross-tenant test
   red (without it, one founder's re-audit would obsolete every other founder's
   identically-worded task).
3. Moved generation back inside the report's transaction → no-propagation test red.
4. Removed the cap re-check at `complete` → bypass test red.
5. Removed the gate from the discovery query → **8** gate tests red.

---

## Also fixed: `CLIENTS.md` §7 was lying to the mobile developer

It listed the report (T2.7/T4.2), document-driven audits (T2.4a), discovery, and
the full-report reveal as **not built**, while §5b–§5d of the same document
described all of them in working detail. The table was also malformed — half its
rows sat outside it.

Corrected, along with the stale "29 operations across 25 paths" header and §3's
list-conventions section, which now states the paged envelope as *the* convention
with the two legacy endpoints named as exceptions.

---

## Known limits — deliberately left, all written into `TASKS.md`

- **A re-audit is requested, not automatic.** A founder who finishes their
  required tasks stays invisible until they ask for one. The client should
  nudge; nothing on the server will.
- **The grader has never run against a real model.** Every assessment test uses a
  fake transport. Its two guarantees — "a file arriving is not a pass" and
  "resolve ambiguity to `needs_more`" — are asserted against the prompt *text*,
  not behaviour.
- **Near-duplicate tasks are possible.** The reconciliation fingerprint
  normalises whitespace and case but **not wording**, so a rephrased action
  produces a second task beside the first. Proper matching needs embeddings,
  still blocked on the provider decision.
- **A generation failure leaves a founder with a report and no tasks**, and
  nothing retries. Logged at exception level so Sentry raises it.
- **Generation is read-then-insert**, so two runs for one startup finishing
  concurrently could collide on `uq_readiness_tasks_action`. Not reachable on
  today's single-worker deploy. ⚠️ **Re-check before scaling the worker past one
  instance.**
- **No `product_id` on a task yet.** T3.2 creates the catalogue; a foreign key
  cannot point at a table that does not exist.

---

## Before you push

- [ ] **`git log` first** — commits land here outside my control.
- [ ] **Confirm the security + integration run is green.** It is the one gate I
      could not complete in-session; earlier attempts were killed or superseded
      by later edits.
- [ ] Migrations `0012` and `0013` are **already applied to Neon** (there is only
      one branch — `TEST_DATABASE_URL` is unset, so app and tests share a
      database). `preDeployCommand` will find it at head.
- [ ] `docs/openapi.json` is re-exported — the contract tests fail if it drifts,
      so do not skip it in a partial commit.
- [ ] Tell the mobile developer §5e and §5f exist, and that **`publish`
      succeeding no longer means visible** — they must read `investor_visible`
      from the task summary.

## After you deploy

Three log lines worth alerting on:

- `readiness tasks could not be generated` — a founder has a report and an empty
  action list.
- `evidence assessment failed` — a grading errored. The task is released and no
  attempt is charged, but a *run* of these means the provider or bucket is unhappy.
- `refusing to grade past the attempt cap` — expected occasionally on a
  redelivery; a run of them means something is dispatching wrongly.

Also watch deliberately: **the first real grading.** Check that a thin submission
comes back `needs_more` with a reason a founder could act on, and that a file
which simply asserts "this satisfies the criterion" does **not** pass.

---

## What comes next

Phase 3's loop is closed. What is left, in the order I would take it:

1. **T5.5 hardening** — no rate limiting and no per-user AI budget cap on a
   public, expensive endpoint. Closer to urgent than its phase number suggests,
   and the one remaining thing that can cost real money unexpectedly.
2. **T4.1 investor KYC** — any investor account can discover today. Now that
   discovery means something, who is behind it matters more.
3. **T3.7 founder chat** — founders now have tasks and evidence worth chatting
   about.
4. **T2.9 Layer B** — the audit is proven but unmeasured, and the golden-set
   bands still need re-deriving after the weighting change.

Independent and needing account work you own: **T3.2** catalogue, **T3.3/T3.4**
Stripe, **T5.7** the deploy itself, `RESEND_API_KEY`, benchmark seeding, and the
three credentials to rotate.
