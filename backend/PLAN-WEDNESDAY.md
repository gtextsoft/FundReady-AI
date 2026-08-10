# Ship plan — Wednesday 2026-08-05

**Written Monday 2026-08-03, 16:10.** Target: live on a public URL, founder
journey + a real investor side.

Share this with the mobile developer. Section 6 is their track and can start now.

---

## 1. Read this first

**Working time is ~14 hours**, not two days. Monday evening + Tuesday + Wednesday
morning. The work below adds up to roughly **18–20 hours of backend effort**, so
something gets cut. Section 7 says what, and when to decide.

**The single most important fact:** an audit today runs, produces a full report,
saves it to the database — and **nothing serves it to anyone**. There is no
endpoint that returns a report to a founder, an investor, or an admin. It was
deliberately deferred, and it is now the thing standing between "we have an AI
audit engine" and "a person can see their audit."

Three other things also make the journey impossible today. None is a code bug:

| Blocker | Effect right now |
|---|---|
| `RESEND_API_KEY` empty | No verification email sends. **Every new account is stuck at `pending_verification` and can never log in.** |
| `APP_LINK_BASE_URL` missing | Even with email working, the verification link points nowhere. |
| `REDIS_URL` empty | **No audit job ever runs.** Every audit sits at `queued` forever. |
| No deploy config at all | No Dockerfile, no render.yaml, no Procfile. The backend has never run anywhere but this laptop. |

So: **nobody can currently sign up, log in, run an audit, or read a result.**
That is the whole of Monday evening and Tuesday morning.

---

## 2. What exists, honestly

| | State |
|---|---|
| Auth, MFA, email verification, password reset | Built, tested, **cannot send email** |
| Startup profile + 27 questions | Built and tested |
| Audit engine (finance, consistency, rubric, synthesis) | Built, 300+ tests, **never run against the live model** |
| Audit API (queue, poll status) | Built, ownership-checked |
| **Serving the report** | **Does not exist** |
| Investor side, brokerage, payments, readiness tasks | **Empty stubs.** 43 lines each — module docstrings only. |
| Deployment | **Does not exist** |

---

## 3. The spine — nothing ships without these

In dependency order. Items marked **[you]** are account/credential actions I
cannot do; please start them now, in parallel with my build.

### A. Unblock the journey — Monday evening (~2h, mostly yours)

1. **[you] Provision Redis** and set `REDIS_URL`. Upstash free tier is fine and
   takes ~10 minutes. *Without this no audit ever runs.*
2. **[you] Get a Resend API key**, verify a sending domain, set
   `RESEND_API_KEY`. *Without this nobody can log in.*
3. **[you] Decide `APP_LINK_BASE_URL`** — the deep link the verification email
   points at. Needs the mobile dev's scheme (e.g. `fundready://verify`).
4. **[me] Run one audit end to end locally** through the real queue and the real
   model. This has never happened. Budget 1h for surprises; it is the first
   time `claude-opus-5` sees the audit prompt.

### B. Serve the report — Tuesday morning (~5h, me) ← **biggest build**

This is T4.2 and it is security-critical: `CLAUDE.md` §4 says tiers are enforced
server-side by dedicated serializers, never by trusting the client.

- Three serializers over the stored report: **founder** (their own full
  actionable report), **investor** (summary only), **SACI admin** (everything).
- `GET /v1/startups/{id}/audits/{run_id}/report` — founder-owned, full.
- Report shape for the client: both verdicts (`level`, `score`, `rationale`),
  `data_integrity_score`, `findings`, `action_plan`, `unevidenced_dimensions`.
- Tests first: an investor hitting a founder's report gets `404`; the summary
  serializer cannot emit a field above its tier.

**Nothing else on this list matters if this is not done.**

### C. Deploy — Tuesday afternoon (~4h, me + you)

- Dockerfile for the API, second process for the RQ worker.
- Render or Fly (Render is faster to stand up; Fly is cheaper to run). **[you]
  create the account and pick one.**
- Production env vars, `alembic upgrade head` against Neon on release.
- CORS for the mobile app origin.
- **[you] set `SENTRY_DSN`** — it is empty, so a live product would have zero
  error visibility.

### D. Investor slice — Tuesday evening / Wednesday morning (~5h, me)

Real, not faked, but scoped to what the summary serializer already gives us:

- Investor registers (the `investor` role already exists and works).
- `GET /v1/startups` — discovery, **summary tier only**, filtered by sector /
  stage / country.
- `POST /v1/startups/{id}/interest` — investor expresses interest.
- `POST /v1/admin/interests/{id}/approve` — SACI admin approves.
- `POST /v1/admin/audits/{run_id}/reveal` — **the SACI reveal**, the only path
  by which an investor ever sees a full report, written to the immutable audit
  log (which already exists).

That is the brokerage claim, end to end, with real tier enforcement.

---

## 4. Things you did not mention that will bite

Ordered by how likely they are to hurt on Wednesday.

1. **No demo data.** A live demo that depends on a 60-second audit finishing on
   stage is a bad bet. I will seed a demo founder with a completed audit so
   there is always something to show. *(30 min — do this.)*
2. **An audit that dies mid-run polls forever.** If the worker restarts or times
   out during a model call, the run stays `running` with no terminal state and
   the mobile app polls indefinitely. On a live product with real users this
   *will* happen. Needs a timeout lease. *(1.5h)*
3. **A redelivered job double-bills.** Two deliveries of the same run both pass
   the guard and both call `claude-opus-5` at high effort. Real money, and the
   second overwrites the first verdict. *(1h, pairs with 2)*
4. **The benchmark table is empty.** Nothing seeds it, so every dimension is
   scored with the model explicitly told to lower its confidence. Scores will
   look mushy and hedged to a judge. *(1h to seed a starter set)*
5. **Dimension weights are ignored.** Declared on all 11 dimensions, read by
   nothing — so fundability and saleability diverge about half as much as
   intended. Real users see slightly wrong scores. *(30 min)*
6. **Tests run against the production database.** `TEST_DATABASE_URL` is unset,
   so the suite falls back to `DATABASE_URL`. Safe today only because every
   fixture rolls back — **not safe once real users have data in there.** Provision
   a second Neon branch before launch. *(15 min)*
7. **Mobile registration is broken.** Every sign-up returns `422`; the client
   does not send `first_name`/`last_name`. One-line fix in the mobile tree.
8. **The four new market/growth questions are not in the mobile form.** Until
   they ship, every real audit is capped at `provisional` — a founder can never
   see a `ready` verdict.
9. **No rate limiting.** Live product, public URL, an expensive AI endpoint. At
   minimum cap audits per user per day.
10. **No repo README aimed at a reader.** If anyone reads the code, this is the
    first thing they open.

---

## 5. Explicitly NOT shipping Wednesday

Saying this now is cheaper than discovering it Tuesday night. All are empty
stubs; each is days-to-weeks, not hours.

| Cut | Why |
|---|---|
| Stripe checkout + subscriptions (T3.3, T3.4) | Payment flows need webhook verification done properly. Rushed payments code is how you leak money. |
| Readiness tasks + evidence upload + re-audit (T3.1, T3.5, T3.6) | The whole Phase 3 loop. Depends on file storage, which is also unprovisioned. |
| Founder and investor AI chat (T3.7, T4.4) | Nice demo, zero effect on the core claim. |
| Document upload driving audits (T2.4a) | R2 unprovisioned. Audits work on typed answers alone. |
| Recommendations, per-country benchmarks (T5.x) | Phase 5. |
| Meeting booking (part of T4.5) | Interest → approve → reveal is the brokerage claim. Calendars are not. |

**If asked on Wednesday:** the honest framing is that the audit engine is the
hard part and it is built and tested; the loop around it is scaffolding.

---

## 6. Mobile developer's track — can start immediately

Nothing here waits on my work.

**Fix first (blocks everything):**
- Send `first_name` and `last_name` in `signUp`. Every registration is `422`
  today. The fields are already collected and validated on your screen.

**Then, in priority order:**
1. **Registration error handling.** Two distinct refusals with different advice:
   `consumer_email_domain` → *"Please use your company email address"*;
   `disposable_email_domain` → *"Please use an address you control privately."*
   Do not collapse them.
2. **Deep link for email verification.** Tell me the scheme so I can set
   `APP_LINK_BASE_URL`. Do not prefetch the link — mail scanners burn the
   single-use token.
3. **Profile form.** 5 columns + 6 required fields gate the audit. Full
   catalogue in `CLIENTS.md` §4a and `FOUNDER-ONBOARDING.md`.
   - Money inputs: show major units, **send integer minor units**. ₦45,000 →
     `4500000`.
   - Percent: `2` for 2%, never `0.02`.
   - `sector` is free text, not a dropdown.
   - `key_person_dependency` is **text, not a boolean**.
4. **The four new market/growth questions** — `market_size_note`,
   `competition_note`, `growth_constraint`, `use_of_funds`. Without these no
   founder can reach a `ready` verdict. `CLIENTS.md` §4a has labels and
   placeholder guidance.
5. **Audit polling.** `POST` returns `202` for new work, `200` if an identical
   audit already exists. Poll `GET .../audits/{run_id}` until `succeeded` or
   `failed`. Back off; do not hammer.
6. **Report screen.** I will publish the schema Tuesday midday. Build against
   these fields: `fundability` / `saleability` each with `level`, `score`,
   `rationale`; plus `data_integrity_score`, `findings[]`, `action_plan[]`.
   - **`insufficient_data` must never render as "not fundable".** It is an
     absence, not a failure. A founder who was never assessed must not think
     they were assessed and rejected.
   - **`provisional` must be visibly labelled provisional**, not shown as a
     plain result. Expect this to be the common case at first.

**Contract:** `docs/openapi.json` is current. Swagger is at `/docs`.

---

## 7. Cut line — decide, do not drift

Check the clock against this. If behind, cut from the bottom.

| Time | Should be done |
|---|---|
| Mon 22:00 | Redis + Resend live; one audit run end to end locally |
| Tue 13:00 | Report serializers + founder report endpoint, tested |
| Tue 18:00 | Deployed to a public URL, migrations applied, one live audit |
| Tue 22:00 | Investor discovery + interest + admin reveal |
| Wed 09:00 | Demo data seeded, benchmarks seeded, smoke test |

**If Tuesday 18:00 arrives and it is not deployed:** stop building the investor
side and finish the deployment. A working founder journey on a real URL beats
two half-features on localhost.

**If Tuesday 13:00 arrives and the report endpoint is not done:** that is the
emergency. Cut the investor side entirely and say so — it is a scoping decision,
not a failure. Everything else is worthless without a visible report.

---

## 8. My recommendation as the person building it

Take the investor side down to discovery + interest + reveal, exactly as scoped
in 3D, and protect the founder spine. The product's claim is *"an AI tells a
founder whether they are fundable, and SACI brokers the introduction."* One
founder getting a real verdict on a real phone from a real URL demonstrates that.
Six half-built investor screens do not.

The two genuinely risky items are **deployment** (never done here, and I cannot
estimate it honestly) and **the first live model call** (the audit prompt has
never been sent — the response may need schema fixes). Both are Tuesday-morning
work for that reason: they need to fail early enough to recover.
