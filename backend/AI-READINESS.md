# FundReady AI — readiness status

**As of 2026-08-04.** Scope: the audit engine (Phase 2) — the part that turns a
Startup Profile into a fundability and saleability verdict. Written for a status
report; every claim here is either verified or explicitly marked as unverified.

---

## Bottom line

**The audit engine now runs end to end against a real model.** On 2026-08-03 a
founder profile went through the queue to `claude-opus-5` and came back with a
persisted, readable verdict — the first time in the project's history. Document
storage followed on 2026-08-04.

That changes the headline from "unproven" to "unmeasured". The pipeline works;
what nobody knows yet is whether its verdicts are *good*, because the accuracy
evaluation has still never been run and the benchmark table it would score
against is empty.

| Question | Answer |
|---|---|
| Can it score a startup? | **Yes — proven live 2026-08-03.** |
| Can a founder trigger an audit over the API? | Yes — the endpoints exist and are ownership-checked. |
| Will the job actually run? | **Yes.** Upstash Redis + worker, proven end to end. |
| Can it read an uploaded pitch deck? | Storage works (2026-08-04); the audit does not yet *read* uploads (T2.4a). |
| Do we know if its verdicts are any good? | **No.** Never measured. |
| Is it safe to show a founder? | Not yet — see *What would go wrong today*. |

---

## What is done and proven

These are built, tested, and the tests exercise the real code path.

| Area | State | Evidence |
|---|---|---|
| **Money and ratios** — margins, burn, runway, CAC/LTV | Done | 49 tests. Computed in code, never by the model, so the numbers cannot drift between runs. |
| **Data-integrity checking** — units, impossible head counts, contradictions | Done | 21 tests. Catches whole naira typed into a kobo field, more founders than staff, churn entered as a fraction. |
| **The rubric** — 11 scored dimensions with explicit criteria | Built | 20 tests through a stubbed model. Criteria are gradeable statements, not adjectives. |
| **Verdict synthesis** — scores → `ready` / `not_yet` / `provisional` / `insufficient_data` | Done | 17 tests. The verdict is computed by rule, not asked of the model, so it is explainable to a founder and reproducible. |
| **Audit API** — queue an audit, poll its status | Built | 10 ownership tests. Another founder's audit returns `404`, never `403`. |
| **Idempotency** — the same inputs never bill twice | Done | Enforced by a database constraint, proven against the live database. |
| **Retry** — a failed audit is retried, capped at 3 attempts | Done | 7 tests, proven to fail against the unfixed code. |
| **Golden set** — 8 hand-scored companies + a determinism harness | Done | 90 tests. Same input always produces the same prompt, the same integrity score, the same verdict. |
| **Security** — tenant isolation, report tiers, auth, throwaway-email blocking | Done | 269 security and auth tests passing. |

**Test totals:** 582 unit tests and 269 security/auth tests currently passing.
Linting, formatting, and type checking are all clean.

---

## What is built but has never run

This is the important distinction for the report. The code exists and is
tested; the *live path* has never been exercised even once.

| Thing | State |
|---|---|
| ~~The background job queue~~ | **Proven 2026-08-03.** Upstash Redis, worker, one audit through to `succeeded`. Found two bugs in doing so — the worker could never fork on Windows, and a connection pool was created per enqueue. |
| ~~The audit prompt against a real model~~ | **Proven 2026-08-03.** `claude-opus-5` at high effort. Verdict: fundability `provisional` 50, saleability `provisional` 46, 44 action items. |
| ~~Document storage~~ | **Proven 2026-08-04.** A real file round-tripped through R2. |
| **Documents feeding the audit** | Storage works, but a run still scores the profile fields only — the extraction stage is not wired into the pipeline (T2.4a). |
| **Transactional email** | `RESEND_API_KEY` is empty. **This is now the blocker: no verification email means no login, for anyone.** Nothing in the settings validation requires it, so the deploy looks healthy while being unusable. |
| **Accuracy measurement** | Deliberately not built. See below. |
| **Error monitoring** | `SENTRY_DSN` is empty, so nothing is reported anywhere. |

---

## What would go wrong today

Found by hand-scoring the golden set this week. These are real defects, not
theoretical ones, and two of them affect what a founder would be told.

1. ~~**`ready` is close to unreachable for a real founder.**~~ **Fixed
   2026-08-03.** A verdict only reads `ready` or `not_yet` if *every* graded
   dimension has evidence, and two of the eleven — market opportunity and
   scalability — were graded against information the form never asked for, so
   almost every real audit came back `provisional`. Four optional questions were
   added (`market_size_note`, `competition_note`, `growth_constraint`,
   `use_of_funds`). **The mobile form needs these four screens before the fix
   reaches a founder.** 17 further criteria remain unserved — see
   `FOUNDER-ONBOARDING.md` for the prioritised list.

2. **The benchmark table has no data in it.** Peer comparison bands are the
   thing that makes a score defensible, and nothing in the repository seeds
   them. With no match, the model is explicitly instructed to lower its
   confidence — which compounds problem 1.
   *Fix: curate and load benchmark rows. Content work, not engineering.*

3. **Dimension weights are defined but ignored.** The rubric declares that some
   dimensions matter more than others; the code averages them all equally. The
   consequence is measurable: fundability and saleability diverge about half as
   much as intended, so a business that is plainly harder to sell than to fund
   does not look that different in its scores.
   *Fix: small code change. Will move every score, so it should land before the
   accuracy run, not after.*

4. **An audit that dies mid-run gets stuck.** If the worker is restarted or
   times out during a model call, the run stays `running` forever and the mobile
   app polls it indefinitely. Retry covers failed runs; it deliberately does not
   cover this one, because re-running blindly would bill the most expensive call
   twice.
   *Fix: a timeout lease on the run. Schema change, small.*

5. **Mobile registration is broken.** Every sign-up from the app currently gets
   a `422` — the backend has required first and last name since 2026-07-30 and
   the client does not send them. Documented for the mobile developer; not fixed
   here, because the mobile app is their tree.

---

## What has not been measured

**We do not know whether the audit's verdicts are good.** That is the single
biggest open question, and it is deliberate rather than an oversight.

The golden set — 8 companies with known-correct answers — now exists and is
scored. Two of the eight are scored by arithmetic alone. The other six were
scored by Claude against the published rubric, which means an evaluation over
those six would partly measure *the model agreeing with itself*. That caveat is
recorded in the data itself so no report can quietly drop it.

`docs/golden-review.md` renders each company the way the audit sees it, with the
figures already worked out, so a human can check or overturn those six scores
quickly. **That review is the highest-value hour anyone can spend on this.**

The paid evaluation run is built up to but not executed, for two reasons: it
costs real money and that is the owner's call, and running it before fixing
items 1–3 above would mostly measure those defects rather than the model.

---

## What remains, in order

| # | Work | Owner | Blocks |
|---|---|---|---|
| 1 | ~~Provision Redis~~ · **done 2026-08-03** | — | — |
| 2 | Add the two missing intake questions | Backend, needs owner sign-off on the form | `ready` being achievable |
| 3 | Load benchmark data | Content / owner | Defensible scores |
| 4 | Apply the dimension weights | Backend | Meaningful fundability vs saleability split |
| 5 | Human-review the 6 drafted golden scores | Owner | Honest accuracy measurement |
| 6 | Build and run the accuracy evaluation | Backend, needs owner spend approval | Knowing if it works |
| 7 | ~~Provision R2 storage~~ · **done 2026-08-04** | — | — |
| 8 | Add the stranded-run lease | Backend | Reliability under restarts |
| 9 | Tune the pass threshold against real results | Backend | Verdicts that mean something |

Items 1–6 are what "the AI is ready" means. Item 7 unlocks document-based
audits, which is a significant capability increase but not a prerequisite —
a founder can complete an audit on typed answers alone.

---

## Phase status

| Phase | State |
|---|---|
| **Phase 0** — project setup | Complete |
| **Phase 1** — auth, profiles, tenancy, uploads | Complete except live email and live file storage |
| **Phase 2** — audit engine | 5 of 10 tasks complete, 4 partial, 1 not started |
| **Phase 3** — readiness loop, tasks, payments | Not started |
| **Phase 4** — investor side and brokerage | Not started |
| **Phase 5** — hardening and deployment | Not started |

"Partial" here consistently means the same thing: the code is written and
tested, and the live path has never been exercised because an external service
is unprovisioned.

---

## One-paragraph version

The AI audit engine is built, thoroughly tested, and **now proven end to end**:
a founder profile goes through a real queue to `claude-opus-5` and comes back
with a persisted verdict, a data-integrity score, and a specific action plan.
Document storage works. What is *not* known is whether the verdicts are any
good — the accuracy evaluation has never been run, and the benchmark table it
would score against is empty, which also suppresses live scores and makes
almost every verdict read `provisional` rather than `ready`. One blocker stands
between this and a founder using it: no transactional email key is set, so
nobody can verify an address and therefore nobody can log in. The remaining
work is that key, benchmark data, the investor brokerage endpoints, and a
deployment — not new engine work.
