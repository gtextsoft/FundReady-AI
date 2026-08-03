# Deploying FundReady on Render

The blueprint is `render.yaml` at the **repository root**, not in `backend/`.
Render only reads it from the root, which is the same rule that left CI
undiscovered for weeks (see `TASKS.md`).

Everything here is a decision you have to make once. It is written in the order
you will hit them.

---

## 1. What gets deployed

Two processes from one repository:

| Service | Type | Start command | Why |
|---|---|---|---|
| `fundready-api` | web | `python -m app` | Answers requests, serves `/docs` |
| `fundready-worker` | worker | `python -m app.workers.queue` | Runs audits off the queue |

**The worker is not optional.** `POST /v1/startups/{id}/audits` queues a job and
returns immediately (D14, `CLAUDE.md` §5). Deploy the API alone and every
submission sits in `queued` forever while founders poll a run nothing will pick
up.

Three managed services stay **outside** Render:

- **Neon** — Postgres. Already holds the data; recreating it as Render Postgres
  would be a migration nobody asked for.
- **Redis** — Render Key Value or Upstash. Left as a plain `REDIS_URL` so the
  blueprint works with either.
- **Cloudflare R2** — document and evidence storage.

---

## 2. Before you touch Render

### 2.1 Generate the two secrets that must be new

These are the only values you must **not** copy from development. Everything
else is a third-party key you already have.

```bash
# JWT_SECRET_KEY -- signs every access token. Below 32 characters the app
# refuses to start in production: a short secret makes tokens forgeable offline.
python -c "import secrets; print(secrets.token_urlsafe(48))"

# MFA_SECRET_ENCRYPTION_KEY -- encrypts TOTP secrets at rest, so a database
# leak alone does not defeat two-factor auth.
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Both are **arbitrary high-entropy strings**. The MFA value in particular is a
passphrase, not a pre-formatted Fernet key — `core/security.py` stretches it
with HKDF precisely so nobody has to know Fernet's key encoding to run the
service. Any long random string works.

Reusing a development `JWT_SECRET_KEY` means anyone who has ever had the dev
`.env` can mint a valid production admin token. That is the whole attack.

**`MFA_SECRET_ENCRYPTION_KEY` cannot be rotated casually.** Every stored TOTP
secret is encrypted under the key derived from it, so changing it makes existing
enrolments undecryptable and every admin has to re-enrol. Choose it once.

### 2.2 Neon: two URLs, not one

Copy both from the Neon dashboard:

- `DATABASE_URL` — the **pooled** endpoint (host contains `-pooler`). The app
  uses it for everything.
- `DATABASE_MIGRATION_URL` — the **direct** endpoint (same host, no `-pooler`).
  Alembic uses it for DDL. The pooled endpoint is PgBouncer in transaction mode
  and is not a supported target for schema changes.

The `postgresql://` form Neon hands you is correct as-is — the app rewrites the
driver prefix itself.

### 2.3 Redis

Either works:

- **Render Key Value** — create it in the dashboard *in the same region as the
  services* and copy the internal URL (`redis://…`). Same-region internal
  traffic is free and unencrypted-by-default, which is fine inside Render's
  private network.
- **Upstash** — copy the `rediss://…` URL. Works from anywhere; adds latency.

**If you are on Upstash, three things to get right.** TLS itself needs no code
change — `Redis.from_url` reads the `rediss://` scheme — but:

1. **Use the Redis-protocol connection string, not the REST endpoint.** Upstash
   shows both. RQ speaks the wire protocol; the REST URL and token will not
   connect, and the error does not say why.
2. **The same URL must be set on both services.** A worker pointed at a
   different Redis from the API is the failure where submissions look accepted
   and nothing ever runs — the exact symptom §4 step 4 tells you to watch for.
3. **Watch the command quota, not just the storage.** An idle RQ worker is not
   free: it blocks on `BLPOP` and sends periodic heartbeats, so a worker left
   running overnight consumes commands while doing nothing. If audits stop
   dispatching for no visible reason, check the quota before the code.

The client sets `health_check_interval` and `socket_keepalive` because managed
Redis closes idle connections and RQ's worker sits in a blocking read for
minutes at a time. Without those, a dropped connection surfaces as a
`ConnectionError` in the middle of an audit rather than a transparent
reconnect.

### 2.4 R2

Create the two buckets and an API token scoped to them. You need
`R2_ACCOUNT_ID`, `R2_ENDPOINT_URL` (`https://<account-id>.r2.cloudflarestorage.com`),
`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_DOCUMENTS`, and
`R2_BUCKET_EVIDENCE`.

**These have never been exercised.** `core/storage.py` is built and unit-tested
but has not written a byte to a real bucket. Budget time for one upload and one
download to shake out a signing or CORS surprise.

---

## 3. Deploy

1. Push `render.yaml` to the default branch.
2. Render Dashboard → **New** → **Blueprint** → pick the repository.
3. Render reads the blueprint and prompts for every `sync: false` variable.
   Fill them in. They land in the `fundready-shared` group, so both services
   get identical values — which is the point of the group.
4. Approve. The web service builds, runs `alembic upgrade head`, then starts.

### Start as `staging`, not `production`

The blueprint sets `APP_ENV=staging` deliberately. Setting `production` turns on
`validate_settings`, which **refuses to boot** unless *every* one of these is
present:

```
DATABASE_URL          APP_LINK_BASE_URL     JWT_SECRET_KEY
MFA_SECRET_ENCRYPTION_KEY                   REDIS_URL
R2_ACCOUNT_ID         R2_ENDPOINT_URL       R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY  R2_BUCKET_DOCUMENTS   R2_BUCKET_EVIDENCE
ANTHROPIC_API_KEY     STRIPE_SECRET_KEY     STRIPE_WEBHOOK_SECRET
```

Note the last two: **no code reads the Stripe keys until T3.3**, but the check
does not know that. Production also enforces the OWASP Argon2 floors. Flip
`APP_ENV` to `production` when the list is genuinely complete — the error names
settings, not causes, so flipping early is a confusing ten minutes.

---

## 4. Verify the deploy

```bash
curl https://<your-service>.onrender.com/v1/health
# {"status":"ok","version":"0.1.0","environment":"staging"}
```

**That 200 proves less than it looks.** `/v1/health` is liveness only: it
deliberately touches neither Postgres nor Redis, so a service with a wrong
`DATABASE_URL` still returns it. A dependency-checking readiness probe is T5.5.

Check the real path instead:

1. Register a founder, verify the email, log in.
2. Create a startup profile with the audit-required fields filled in.
3. `POST /v1/startups/{id}/audits` → expect `202` and `status: "queued"`.
4. Watch the **worker** log stream. You should see `worker starting`, then the
   job. If the run stays `queued`, the worker is not running or `REDIS_URL`
   differs between the two services.
5. Poll `GET /v1/startups/{id}/audits/{run_id}` until `succeeded`.
6. `GET /v1/startups/{id}/audits/{run_id}/report` → the verdict, scores,
   findings and action plan. **`404` before the run succeeds** — that is
   correct, not a bug; a report does not exist until there is one.

Step 5 spends real money — one `claude-opus-5` call at high effort. That is the
smallest end-to-end proof there is; there is no cheaper way to learn that the
queue, the worker, the database, and the API key all work together.

**Expect `provisional`, not `ready`.** With an empty benchmark table the rubric
is told to lower its confidence on every dimension, and a verdict needs *every*
in-scope dimension evidenced to read `ready` or `not_yet`. A `provisional`
result on the first live run means the pipeline worked; it is not a failure to
debug.

---

## 5. Things that will bite

**This costs money before it serves a request.** The blueprint sets
`plan: starter` on **both** services, and that is not padding:

- `preDeployCommand` — how migrations run — is [available only on paid instance
  types](https://render.com/changelog/predeploy-command). On free you would run
  `alembic upgrade head` by hand against the direct URL before every deploy.
- Free web services sleep when idle, so the mobile client's first call after a
  quiet period times out.

If you want to trim, trim the web service, not the worker: an API that sleeps is
an annoyance, a worker that is missing means audits never run at all.

**Nothing requires email to be configured, and without it nobody can log in.**
`RESEND_API_KEY` and `EMAIL_FROM_ADDRESS` are **absent from
`missing_production_settings`**, so even `APP_ENV=production` boots happily
without them. The failure is silent and total: registration succeeds, the
account sits at `pending_verification`, the verification email never sends, and
the founder can never authenticate. There is no error to read — the deploy looks
healthy. Set both before you let anyone near it, and send yourself one real
verification email as part of §4 step 1.

Same shape for `APP_LINK_BASE_URL`: it *is* required in production, but in
staging a blank value produces emails whose links point nowhere.

**CI does not deploy.** `.github/workflows/ci.yml` runs lint, types, tests, and
a secret scan. Render deploys on push to the default branch independently of
whether CI passed. If you want CI to gate deploys, turn off auto-deploy and use
a deploy hook from the workflow.

**A green CI badge skips every database-backed test.** The runner has no
`DATABASE_URL`, so all ten `requires_database` files skip — including tenant
isolation and ownership. For a codebase whose §4 is non-negotiable that is the
gap worth closing first: add a throwaway Neon branch as a `TEST_DATABASE_URL`
repository secret.

**The worker holds no request context.** Errors there never reach a user. Set
`SENTRY_DSN` or accept that a failed audit is visible only as a `failed` run and
a log line nobody is watching.

**Neon scales to zero.** The first request after idle pays a cold start. The
engine sets `pool_pre_ping` so a stale connection is revived rather than
failing, but the latency is real.

**Free-tier web services sleep.** A sleeping API means the mobile client's first
call times out. Starter or above for anything a client depends on.

---

## 6. What this deployment does *not* do yet

Deploying today gets you: auth (register, login, refresh, email verification,
password reset, MFA), startup profiles, document upload to R2, the admin
benchmark KB, audits that run end-to-end, **and the report they produce** —
`GET /v1/startups/{id}/audits/{run_id}/report` for the founder and the
admin-only path for SACI (T4.2, 2026-08-03).

It does **not** get you:

- **Document-driven audits.** Uploads are stored but not yet read by the audit
  (T2.4a); a run scores the profile fields only.
- Readiness tasks, evidence, Stripe, investor discovery, brokerage — Phases 3–5.
- Rate limiting, per-user AI budget caps, RLS (T5.5, D19).

The AI budget point deserves emphasis: `ai/client.py` **measures** spend and
nothing **caps** it. A deployed, publicly reachable audit endpoint can be
submitted to repeatedly. The idempotency constraint stops repeats of *identical*
inputs; it does nothing about a caller who edits one field between submissions.
Until T5.5 lands, keep registration closed or watch the Anthropic dashboard.
