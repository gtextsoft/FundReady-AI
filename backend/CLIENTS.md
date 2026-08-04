# FundReady — Client Integration Guide

For the developers building against this API. **Three roles across two
surfaces:**

| Role | Surface | What they do |
|---|---|---|
| **Founder** | Mobile | Submits a startup profile and documents, gets an audit, completes readiness tasks |
| **Investor** | Mobile | Discovers startups as **summaries**, chats with an analyst, books meetings |
| **Admin (SACI)** | **Web** | Brokers everything; the only role that can reveal a full report |

You do not need repo access to use this document. Everything here is checked
against the running API — `tests/unit/test_client_guide.py` fails if a path or
enum named below stops existing.

- **Swagger UI:** `/docs` · **ReDoc:** `/redoc` · **Raw spec:** `/openapi.json`
- **Exported spec:** [`docs/openapi.json`](docs/openapi.json), committed so you
  can generate a client without running the server.
- Everything is under **`/v1`**. `GET /v1/health` needs no auth and is the
  fastest way to confirm you are pointed at the right environment.

---

## 1. Authentication

Bearer tokens. Send the access token on every authenticated request:

```http
Authorization: Bearer <access_token>
```

| Token | Lifetime | Notes |
|---|---|---|
| Access | **15 minutes** | Short by design. Expect to refresh often. |
| Refresh | **30 days** | Single-use — see rotation below. |
| MFA challenge | **5 minutes** | Not an access token. Grants nothing on its own. |

### The flow

```
POST /v1/auth/register        → 202  { status: "pending_verification" }
   (user receives an email)
POST /v1/auth/verify-email    → 200  account becomes active
POST /v1/auth/login           → 200  LoginResponse   ← branch on `status`
POST /v1/auth/mfa/verify      → 200  TokenPairResponse   (only if mfa_required)
POST /v1/auth/refresh         → 200  TokenPairResponse   (rotates both tokens)
POST /v1/auth/logout          → 204  revokes the whole family
```

**Branch on `LoginResponse.status`.** It is not always tokens:

- `"authenticated"` → `tokens` is populated, you are done.
- `"mfa_required"` → `tokens` is `null` and `mfa_token` is set. Send that
  `mfa_token` plus the 6-digit code to `POST /v1/auth/mfa/verify`.

A client that assumes `tokens` is always present will crash on every
MFA-enrolled account — which is **every admin**, so the web app hits this path
100% of the time.

### Refresh rotation and reuse detection — read this one

Refresh tokens are **single-use**. Every successful refresh returns a *new*
refresh token and invalidates the one you sent.

If a refresh token is ever presented **twice**, the server treats it as theft
and revokes the entire token family — that session is dead and the user must
log in again. This is a security feature (`AUTH.md` §6), not a bug, but it
punishes two very common client mistakes:

1. **Concurrent refreshes.** Three requests 401 at once, each fires its own
   refresh, two of them replay a consumed token → session killed. **Serialise
   refresh through a single-flight mutex** and have queued requests await the
   one in-flight refresh.
2. **Retrying a failed refresh** with the same token. Don't. If a refresh
   fails, send the user to login.

Persist the rotated refresh token **before** using the new access token — if
the app is killed in between, the stored token is already consumed and the
user is logged out for no reason.

### 401 vs 403 — they mean different things

| Status | Meaning | What the client should do |
|---|---|---|
| **401** `unauthenticated` | Missing, malformed, or expired access token | Refresh **once**, retry. If that fails, log out. |
| **403** `forbidden` | Authenticated, but not permitted | **Do not refresh. Do not retry.** Show the user a message. |

Refreshing on a 403 is the most common integration bug: the token is fine, the
*role* is wrong, and retrying loops forever.

### MFA

- Any user may enrol: `POST /v1/auth/mfa/enroll` → returns a base32 `secret`
  and an `otpauth://` `provisioning_uri` to render as a QR code. **Enrolment is
  not active yet.**
- `POST /v1/auth/mfa/confirm` with one valid code activates it and returns
  **10 recovery codes, shown exactly once** — they are stored hashed and cannot
  be re-displayed. The web app must make the user save them before dismissing.
- **Admins are a special case.** An admin who has not enrolled MFA can log in
  and get a token, but **every admin-only endpoint returns 403** until they do.
  That is deliberate: it resolves the bootstrap problem (enrolling requires
  being logged in) without granting admin capability early. The admin web app
  should detect `403` on first admin call and route to enrolment.

---

## 2. The error envelope

**Every** non-2xx response has this exact shape. There are no other error
formats:

```json
{
  "error": {
    "code": "forbidden",
    "message": "You do not have access to this resource.",
    "details": null
  }
}
```

**Branch on `code`, never on `message`.** Codes are stable and part of the
contract; messages are for humans and will change without notice.

| `code` | HTTP | Meaning |
|---|---|---|
| `unauthenticated` | 401 | No valid access token — refresh once |
| `forbidden` | 403 | Wrong role, or not your resource — do not retry |
| `not_found` | 404 | No such resource, **or** one you may not see |
| `conflict` | 409 | Already exists, or state does not allow this |
| `validation_error` | 422 | Body failed validation — see `details` |
| `payload_too_large` | 413 | Body or file exceeds the limit |
| `method_not_allowed` | 405 | Wrong verb for that path |
| `rate_limited` | 429 | Back off and retry later |
| `service_unavailable` | 503 | Dependency down — retry with backoff |
| `internal_error` | 500 | Our bug. Report it with the request id. |

`404` doubles as "not yours" on purpose: telling an investor that a startup
exists but is not visible to them leaks its existence. Do not present 404 on a
resource the user just created as data loss — it is far more likely a
permission boundary.

Every response carries a request-correlation header. Include it in bug reports;
it is how a failure gets traced server-side.

---

## 3. Conventions

These hold across every endpoint. Assume them rather than checking per-route.

- **Timestamps** — ISO 8601, always UTC, always `Z`-suffixed:
  `2026-07-29T09:15:00Z`.
- **Money** — **integer minor units**, never floats. `net_burn_minor: 250000`
  with `currency: "NGN"` means ₦2,500.00. Never do float arithmetic on money.
- **Currency** — ISO 4217 (`NGN`, `USD`, `AED`, `GBP`). There is **no FX
  conversion** anywhere in the API; figures are reported in the currency they
  were submitted in.
- **Identifiers** — UUIDs as strings.
- **Unknown fields are rejected.** Request bodies use `extra="forbid"` — sending
  a field the schema does not declare is a `422`, not a silent ignore. Do not
  echo a response object back as a request body.
- **Additive change only.** New optional response fields can appear at any time;
  parse leniently and ignore what you do not recognise. Breaking changes get a
  new version and a `CHANGELOG` entry.

### List conventions — not yet consistent

Read this before writing a generic list helper: **the two list endpoints do not
agree with each other**, so a shared abstraction built today will be wrong for
one of them.

| Endpoint | Query parameters |
|---|---|
| `GET /v1/benchmarks` | `sector`, `stage`, `metric`, `region`, `include_retired`, `limit`, `offset` — all optional |
| `GET /v1/startups/{id}/documents` | **none** — returns every document for that startup |

`limit`/`offset` paging exists only on benchmarks (admin web). Neither endpoint
takes a sort parameter, and neither returns a total count, so there is no way to
render "page 3 of 12" — paginate with a cursor-style "load more" instead.

`CLAUDE.md` §6 requires list conventions to be consistent across every list
endpoint. They are not, and this is documented rather than papered over; it is
tracked as an open follow-up in `TASKS.md`. Expect `documents` to gain paging
before Phase 3 adds more collections.

---

## 4. Endpoints by role

29 operations across 25 paths today. Anything not listed here is not built yet
— see §7.

### Public (no token)

| | |
|---|---|
| `POST /v1/auth/register` | Founder or investor only. **Admins cannot self-register.** |
| `POST /v1/auth/login` | Returns `LoginResponse` — branch on `status` |
| `POST /v1/auth/refresh` | Rotates the pair |
| `POST /v1/auth/logout` | Revokes the family |
| `POST /v1/auth/verify-email` | Token from the emailed link |
| `POST /v1/auth/password-reset/request` | Always 202, even for unknown addresses |
| `POST /v1/auth/password-reset/confirm` | Completing this **logs out every session** |
| `POST /v1/auth/mfa/verify` | Completes an `mfa_required` login |
| `GET /v1/health` | Liveness |

### Any signed-in user

| | |
|---|---|
| `GET /v1/users/me` | The caller's own account, never another's |
| `POST /v1/auth/mfa/enroll` · `POST /v1/auth/mfa/confirm` | Enrol a second factor |

### Founder (mobile)

| | |
|---|---|
| `POST /v1/startups` | Founder or admin. Owner comes from the token, never the body. |
| `GET /v1/startups/me` | Your own profile |
| `GET /v1/startups/{id}` · `PATCH /v1/startups/{id}` | Ownership-checked |
| `POST /v1/startups/{id}/documents` | Step 1 of upload — see §5 |
| `POST /v1/documents/{id}/complete` | Step 3 of upload |
| `GET /v1/startups/{id}/documents` | List |
| `GET /v1/documents/{id}/download` | Expiring signed URL |
| `POST /v1/startups/{id}/publish` · `POST /v1/startups/{id}/unpublish` | Opt in or out of investor discovery — see §5c |
| `POST /v1/startups/{id}/audits` | Request an audit — see §5a |
| `GET /v1/startups/{id}/audits` | This startup's runs, newest first |
| `GET /v1/startups/{id}/audits/{run_id}` | Poll one run's status |

If you omit `name` on profile creation it is derived from your company email
domain — `founder@acme.com` → `Acme`. That is a starting point, not a verified
company name; send `name` explicitly to control it.

### Admin only (web) — 403 until MFA is enrolled

| | |
|---|---|
| `POST /v1/admin/users` | Provision another admin |
| `POST /v1/admin/users/{id}/suspend` · `POST /v1/admin/users/{id}/reactivate` | Suspension bumps `session_valid_after`, killing live sessions |
| `PATCH /v1/admin/users/{id}/role` | Change a role |
| `GET /v1/benchmarks` · `GET /v1/benchmarks/{id}` | Browse and read the benchmark KB |
| `POST /v1/benchmarks` · `PATCH /v1/benchmarks/{id}` · `POST /v1/benchmarks/{id}/retire` | Create, revise, retire |
| `GET /v1/admin/startups/{startup_id}/audits/{run_id}/report` | Any startup's report **in full** — see §5b |

**The admin report path is separate from the founder's on purpose.** It is the
same stored document served by a wider serializer, and keeping it on its own
route means a change to the founder endpoint cannot silently widen what an
admin-shaped request returns — or the reverse. It is the read behind the
brokerage: an investor never reaches a full report through their own
entitlement, only through a SACI reveal at the meeting.

**All five benchmark endpoints are admin-only, including the reads.** Two
reasons, and the second is easy to miss: a founder who could *write* benchmarks
could move the goalposts they are judged against, and a founder who could
merely *read* them would know exactly what to claim. The guard lives in the
service layer, so the route signature alone does not show it — the endpoint
descriptions do.

> **Note for the admin web app:** benchmarks are *retired*, never deleted. An
> audit cites what it scored against, so the row must survive.

---

## 4a. Founder onboarding, end to end

Everything a founder is asked, in the order you should ask it. Steps 1–3 are
required before an audit can run; steps 4–5 are how the profile gets good enough
to produce a verdict rather than `insufficient_data`.

```
1. POST /v1/auth/register          → account (founder, company email only)
2. POST /v1/auth/verify-email      → email proven, account usable
3. POST /v1/startups               → profile created (5 required columns)
4. PATCH /v1/startups/{id}         → fill in the question catalogue below
5. POST /v1/startups/{id}/documents → deck + financials (§5)
6. POST /v1/startups/{id}/audits   → submit, then poll (§5a)
```

### Step 1 — Register

`POST /v1/auth/register` with `email`, `password`, `role: "founder"`,
`first_name`, `last_name`.

> ⚠️ **This is currently broken for the mobile client.** `first_name` and
> `last_name` have been required since 2026-07-30 and `signUp` in
> `frontend/src/api/http.ts` does not send them, so every mobile registration
> returns `422`. The sign-up screen already collects and validates both — the
> two lines just need restoring in the request body.

**Two domain rules apply, and they are not the same rule.** Both return `422`
with `details.reason`, so branch on that:

| `reason` | Applies to | Means |
|---|---|---|
| `consumer_email_domain` | **Founders only** | gmail, yahoo, outlook and similar. Investors are exempt — an angel investing personally has no company domain (D20). |
| `disposable_email_domain` | **Everyone** | A throwaway inbox: mailinator, 10minutemail, guerrillamail and similar. No role is exempt. |

The second one is stricter on purpose. Most throwaway inboxes are **publicly
readable** — a mailinator address has no password — so an account on one hands
its verification link, and every future password-reset link, to anyone who knows
the address. That is account takeover, not a weak identity signal, which is why
it applies to investors too.

Three things follow for your UI:

- **Validate before submitting.** A founder who types their gmail address and is
  rejected three fields later has a bad first experience. Reject inline:
  *"Please use your company email address — we use your domain to identify your
  business."*
- **Show different help for the two reasons.** "Use your company address" is
  wrong advice for a throwaway domain; the user needs *"Please use an address
  you control privately."* Do not collapse them into one message.
- **The domain becomes the first company name on the profile.** `acme.com` →
  "Acme". Pre-fill the profile `name` field at step 3 and let the founder
  correct it. Refused domains return no name, so there is nothing to prefill.

Password: at least 12 characters, and must not contain the email address.

### Step 2 — Verify email

The account exists but is not usable until the address is proven. The link in
the email points at `APP_LINK_BASE_URL` — your deep link, not the API — and your
handler calls `POST /v1/auth/verify-email` with the token from the URL.

Tokens are **single-use and expire in 24 hours**. Do not prefetch or preview the
link anywhere: mail scanners that follow URLs will burn the token before the
founder taps it.

### Step 3 — Create the profile

`POST /v1/startups`. Every field is optional — a founder can start with just a
name — but these five are the indexed columns an audit needs, and they are the
ones to ask for on the first screen:

| Column | Ask | Notes |
|---|---|---|
| `name` | "What is your business called?" | Pre-fill from the email domain |
| `sector` | "What sector are you in?" | **Free text, not a dropdown.** D11 requires accepting sectors that don't exist yet. Offer suggestions, allow anything. |
| `stage` | "What stage are you at?" | Enum, see §6: `idea`, `pre_seed`, `seed`, `series_a`, `series_b_plus`, `growth` |
| `country` | "Where is the business registered?" | ISO 3166-1 alpha-2, e.g. `NG` |
| `currency` | "What currency do you report in?" | ISO 4217, e.g. `NGN` |

### Step 4 — The question catalogue

Everything else lives in a `fields` object. Each entry is
`{"value": ..., "source": "founder"}` — send `source: "founder"` for anything a
person typed. (`document` and `inferred` are what extraction writes; you never
send those.)

```json
{
  "fields": {
    "description": { "value": "Same-day parcel delivery for Lagos merchants.", "source": "founder" },
    "monthly_revenue_minor": { "value": 4500000, "source": "founder" }
  }
}
```

**Required for an audit** — the profile is not auditable without these six, and
`missing_fields` will keep naming them until they are present:

| Field | Ask the founder | Type |
|---|---|---|
| `description` | "What does your business do?" | text |
| `business_model` | "How do you make money?" | text |
| `team_size` | "How many people work on this, including founders?" | integer |
| `monthly_revenue_minor` | "Revenue in your most recent full month" | money |
| `monthly_costs_minor` | "Total operating costs in that same month" | money |
| `cash_on_hand_minor` | "How much cash do you have available right now?" | money |

**Everything else** — optional, but each one that is missing is a dimension the
audit has less to go on, and thin data yields `insufficient_data` rather than a
verdict. Worth prompting for, not worth blocking on:

| Field | Ask the founder | Type |
|---|---|---|
| `website` | "Do you have a website?" | text |
| `founded_year` | "What year did the business start trading?" | year |
| `founder_count` | "How many founders are there?" | integer |
| `founders_full_time` | "How many founders work on this full time?" | integer |
| `cost_of_revenue_minor` | "What does it cost you directly to deliver that revenue?" | money |
| `last_12m_revenue_minor` | "Revenue over the last twelve months" | money |
| `active_customers` | "How many paying customers do you have today?" | integer |
| `monthly_active_users` | "How many monthly active users?" | integer |
| `customer_acquisition_cost_minor` | "On average, what does it cost to win one customer?" | money |
| `average_revenue_per_customer_minor` | "On average, how much does one customer pay you per month?" | money |
| `monthly_churn_percent` | "What share of customers do you lose each month?" | percent |
| `total_raised_minor` | "How much have you raised to date?" | money |
| `current_raise_target_minor` | "How much are you raising now, if anything?" | money |
| `cap_table_summary` | "Who owns what, in summary?" | text |
| `ip_owned` | "Does the business own its core intellectual property?" | boolean |
| `contracts_transferable` | "Would your customer contracts survive a change of ownership?" | boolean |
| `key_person_dependency` | "What breaks if a specific person leaves?" | **text, not a yes/no** |

The last three exist because the PRD audits **saleability** as well as
fundability. Do not merge them into the funding screen — a founder answers them
differently when they understand they are being asked what happens if they sell.

**New on 2026-08-03 — four market and growth questions.** Additive and optional;
nothing existing changed. They exist because two of the eleven dimensions the
audit grades — market opportunity and scalability — had **no question behind
them**, so both came back unevidenced on almost every profile. A verdict needs
every in-scope dimension evidenced to read `ready` or `not_yet`, so the practical
effect was that a founder could answer everything else perfectly and still be
capped at `provisional`. **Until these four screens ship, that cap stays.**

| Field | Ask the founder | Type |
|---|---|---|
| `market_size_note` | "How big is the market you can actually serve today, and how did you work that out?" | text |
| `competition_note` | "Who else solves this problem for your customers today?" | text |
| `growth_constraint` | "What is limiting your growth right now, and what have you already proven you can do about it?" | text |
| `use_of_funds` | "If you raised money, what would it buy?" | text |

Three notes for the UI, because these four are graded on substance rather than
on being non-empty:

- **Show a worked example as placeholder text on `market_size_note`.** It has to
  elicit a number, how it was derived, and what bounds it today — e.g. *"12,000
  registered pharmacies in Lagos × ₦5,000/month = ₦60m/month. We can't serve
  other states yet, each needs its own council registration."* "Huge" scores
  nothing.
- **Do not merge `growth_constraint` and `use_of_funds`.** Naming the bottleneck
  and saying what money buys are separate claims, and the audit grades whether
  the second maps onto the first.
- **Ask `use_of_funds` wherever you ask `current_raise_target_minor`.** The
  amount on its own is not evidence of anything; it becomes meaningful only
  next to what the money is for.

A good place for all four is a second screen after the required core, or as a
post-audit follow-up — see the staging note at the end of
`FOUNDER-ONBOARDING.md`, which explains how to use the audit's own
`unevidenced_dimensions` to ask only the questions that would change *this*
founder's result.

### Validation the UI should enforce

These are rejected server-side with `422`; enforcing them client-side saves a
round trip and gives a better message.

| Type | Rule | The mistake to prevent |
|---|---|---|
| **money** | Integer in **minor units** — kobo, cents. `₦45,000.00` is `4500000`. | Sending `45000` for ₦45,000, which is 100x light. Show a formatted major-unit field and convert on submit; never make the founder type kobo. |
| **percent** | A number `0`–`100`. `2.5` means 2.5%. | Sending `0.025` for 2.5%. The server accepts it — it is a valid number in range — and it becomes a churn figure 100x too low, which inflates lifetime value. Nothing downstream can tell it apart from a genuinely low-churn business. **Label the input `%` and reject fractions.** |
| **integer** | Whole number, not negative. `true` is refused. | — |
| **year** | Four digits, 1800–2100. | — |
| **boolean** | `true`/`false` only. | — |
| **text** | Any string. | Sending `true` for `key_person_dependency`. It is a description, not a flag. |

Money and percent are the two that fail silently: a wrong value is accepted,
audited, and produces a wrong verdict. The consistency stage catches some of it
(§5a findings) but only when another field disagrees by 10x or more.

### `missing_fields` drives the completion UI

Every profile response carries `missing_fields` — the required fields still
absent, considering both the five columns and the `fields` document. Use it
directly as the checklist on a "complete your profile" screen, and as the gate
on the "Request audit" button: submitting an incomplete profile returns `422`
with the same list in `details.missing_fields`.

---

## 5. Document upload (three steps)

Files never pass through this API — they go straight to object storage.

```
1. POST /v1/startups/{id}/documents   → 201 UploadTicket { upload_url, document_id, ... }
2. PUT  <upload_url>                  → direct to storage. Send the EXACT
                                        content_type you declared in step 1.
3. POST /v1/documents/{id}/complete   → 200 confirms the upload
```

Note the asymmetry: step 1 returns **201** (it creates a document record), step
3 returns **200** (it updates one).

Three things that will bite you:

- **The declared `content_type` is pinned into the signature.** Uploading with
  a different one fails at the storage layer, not here.
- **Size is checked after the fact.** A presigned PUT cannot enforce a size
  limit, so an oversized file uploads successfully and is then deleted
  server-side. Check the size client-side before starting.
- **The allowlist constrains what you *declare*, not the bytes.** Real content
  inspection belongs to the scanner, which is **not built yet** (T5.5).

### Do not gate on `scan_status == "clean"`

`clean` is never set today. No scanner is wired, so every upload settles at
**`skipped`** — the honest value, chosen deliberately over marking an unscanned
file `clean`, which would later read as a completed check that never happened.

Downloads check **two independent things**, and neither is `clean`:

1. `status` must be `ready` — i.e. step 3 completed. A `pending` or `rejected`
   document is refused with `422` and `reason` set to that status.
2. `scan_status` must not be `infected` — refused with `422` and
   `reason: "infected"`.

So the correct client rule today is **gate on `status == "ready"`, and treat any
`scan_status` other than `infected` as usable.** Revisit when T5.5 ships. A
client written to wait for `clean` blocks forever on every document ever
uploaded.

Downloads are the mirror image: `GET /v1/documents/{id}/download` returns a
short-lived signed URL, not the bytes.

---

## 5a. Running an audit (submit, then poll)

An audit is minutes of model time, so it never runs inside your request.

```
1. POST /v1/startups/{id}/audits                 → 202 AuditRun { id, status: "queued" }
2. GET  /v1/startups/{id}/audits/{run_id}        → poll until status is terminal
3. GET  /v1/startups/{id}/audits/{run_id}/report → the verdict, once succeeded
```

**Poll no faster than every 5 seconds**, and back off after the first minute. A
run typically finishes in under two.

### The status codes carry meaning here

| Code | Means |
|---|---|
| `202` | Queued. New work was created. |
| `200` | **An audit of these exact inputs already exists** — the same run is returned. Read its `status`: see below. |
| `422` | The profile is missing fields the audit needs. `details.missing_fields` lists them. |
| `404` | No such startup, or not yours. |

The `200` is not an error and not a race — it is the idempotency guarantee. An
audit is the most expensive operation the platform performs, so submitting an
unchanged profile twice returns the first verdict rather than buying a second
one. **Change the profile and the next submission is a new run.** If you want a
"re-run" button, it belongs behind a profile edit, not next to it.

**A `200` does not tell you whether work was queued — the run's `status` does.**
Resubmitting a `failed` run is the retry path (see below), so a `200` carrying
`status: "queued"` means that run was just re-dispatched. A `200` carrying
`succeeded` or `running` means nothing new was queued. Branch on `status`, never
on the fact that you got a `200`.

### Terminal states

`succeeded` and `failed` are terminal; `queued` and `running` mean keep polling.
A `failed` run carries `error_code` (stable — branch on this) and
`error_message` (founder-safe prose — show it, do not parse it).

**Retrying a failed run means submitting again.** POST to the same endpoint with
the profile unchanged: the run keeps its id, returns to `queued`, and is
re-dispatched. You get a `200` (the run already existed), its `error_code` and
`error_message` clear, and polling resumes as normal.

Retries are capped. After a small number of attempts the run stays `failed` with
`error_code: "audit_retries_exhausted"` and submitting again does nothing —
an audit is the platform's most expensive operation, and an uncapped retry
button would bill a founder a full pass per tap. Surface that code as "contact
support", not as "try again". `error_code: "audit_requeue_failed"` is the
transient sibling — the retry could not be dispatched, and submitting again is
the correct response.

### The status endpoint never returns the report

`AuditRun` is lifecycle only. There is deliberately no `report` field on it in
any state — a status poll is reachable long before a report exists, and the
report is served by its own per-tier serializer.

### 5b. Reading the report

`GET /v1/startups/{startup_id}/audits/{run_id}/report`

**`404` until the run has succeeded.** A report does not exist while a run is
`queued`, `running`, or `failed`. Do not call this until polling returns
`succeeded`; an empty `200` would have you rendering a blank verdict as a real
one, which is why it is a `404` instead.

```json
{
  "rubric_version": "v1",
  "data_integrity_score": "85",
  "fundability": {
    "scope": "fundability",
    "level": "provisional",
    "score": 58,
    "sufficiency": "provisional",
    "rationale": "Provisional: scored 58 out of 100 …",
    "evidenced_dimensions": ["financial_health", "unit_economics"],
    "unevidenced_dimensions": ["market_opportunity", "scalability"]
  },
  "saleability": { "…": "same shape" },
  "findings": [
    {
      "code": "churn_implausibly_low",
      "severity": "likely",
      "fields": ["monthly_churn_percent"],
      "message": "Your monthly churn is under 0.1% …"
    }
  ],
  "action_plan": [
    { "dimension": "legal_and_ip", "action": "Obtain a signed IP assignment …", "dimension_score": 40, "is_priority": true }
  ]
}
```

**Three rendering rules that are not style preferences.** Getting these wrong
tells a founder something untrue about their business.

1. **`insufficient_data` must never render as "not fundable".** It is an
   *absence*, not a failure — the assessment was not made. A founder who reads
   it as a rejection has been told they failed something that never ran. Use
   wording like *"We could not assess this yet"* and show
   `unevidenced_dimensions` as what to fill in.
2. **`provisional` must be visibly labelled provisional**, never shown as a
   plain result. **Expect this to be the common case**, not the exception.
3. **`score` is `null` whenever the level is `insufficient_data`. Do not coerce
   it to `0`.** A zero renders as "scored 0 out of 100", which is the same false
   rejection as rule 1 wearing a number.

`data_integrity_score` is a **string**, not a float — it is a `Decimal`
server-side and JSON floats would change the value. Parse it as a decimal or
display it as given. Below `50` no verdict is formed at all and both levels read
`insufficient_data`: the submitted figures disagree with each other too much to
score, and `findings` says which ones.

`action_plan` is already ordered worst-first, with unassessable dimensions
ahead of low-scoring ones. Render it in the order given.

**`is_priority` is the short list — render those first, behind a "show
everything" affordance.** A real audit produced **44 items**, all of them
specific and correct, and a founder shown 44 acts on none of them. At most five
are marked, one from each of the worst five dimensions, so the short list is
five different things to do rather than five ways of describing one weakness.
Nothing is truncated server-side: the array still contains every item, and
hiding the rest permanently would hide work the founder has to do. A report
produced before this field existed has no `is_priority: true` at all — treat an
empty short list as "show the full list".

`severity` is `certain` (arithmetically impossible — cannot be a false positive)
or `likely` (crossed a threshold — a real business could look like this). Word
`likely` findings as questions, not accusations.

**Another founder's run returns `404`, never `403`.** Investors have no access
to this endpoint at all; they see summary-tier data through discovery, and a
full report only through a SACI reveal at the meeting.

---

## 5c. Investor discovery (T4.3)

Two sides, two audiences. The founder controls whether they appear; the investor
browses what founders have published.

### Founder side — publishing

| | |
|---|---|
| `POST /v1/startups/{id}/publish` | Opt in to discovery |
| `POST /v1/startups/{id}/unpublish` | Opt out again, immediately |

**Publishing is consent, not eligibility, and the difference matters for your
UI.** Opting in says the founder is willing to be seen. Whether there is
anything to *show* is decided separately: a startup appears in discovery only
once it also has a **succeeded audit**.

So publishing before the first audit finishes is allowed and is **not an
error**. Say so plainly — *"You'll appear to investors once your audit
completes."* Poll the audit, not the publish endpoint. `investor_visible` and
`published_at` are on every `ProfileResponse`.

Unpublishing is unconditional and takes effect at once. It does **not** retract
a report SACI has already revealed to an investor: that disclosure happened, and
the audit log keeps it.

### Investor side — browsing

| | |
|---|---|
| `GET /v1/discover` | Browse published startups, newest first |
| `GET /v1/discover/{startup_id}` | One card |

**Investors and SACI admins only — `403` for a founder.** Founders do not browse
each other.

Filters: `sector` (case-insensitive, because sector is free text), `stage`,
`country`, plus `limit` (1–100, default 20) and `offset`. The response carries
`total` ignoring pagination, so you can render "page N of M".

A card is **summary tier** and carries only:

```json
{
  "startup_id": "…", "name": "Kanmi Pay", "sector": "fintech",
  "stage": "seed", "country": "NG",
  "audit_run_id": "…", "rubric_version": "v1",
  "fundability": { "scope": "fundability", "level": "ready", "score": 78 },
  "saleability": { "scope": "saleability", "level": "not_yet", "score": 61 },
  "published_at": "2026-08-03T12:00:00Z"
}
```

**What a card never carries, and do not build UI expecting it:** the founder's
name or contact details, any submitted figure (revenue, costs, runway, customers,
churn), the verdict rationale, the findings, the action plan, or the
data-integrity score. That is the brokerage — the verdict is enough to decide
whether to ask for an introduction, and not enough to skip one.

The same rendering rules as §5b apply to `level`: **`insufficient_data` must
never read as "not fundable"**, and `provisional` must be labelled provisional.

An unpublished startup returns **`404`**, identical to one that does not exist —
a distinguishable answer would let a caller test which startup ids are real.

---

## 5d. Brokerage — interest, approval, reveal (T4.5, T4.6)

**SACI stands between the two sides, and the API enforces it.** An investor
never reaches a founder's full report by their own entitlement.

```
1. POST /v1/discover/{startup_id}/interest      investor asks for an intro
2. POST /v1/admin/interests/{id}/approve        SACI agrees to broker it
3. POST /v1/admin/interests/{id}/reveal         SACI opens ONE report
4. GET  /v1/interests/{id}/reports/{run_id}     investor reads it
```

### Approval is not disclosure — build the UI this way

Step 2 and step 3 are **separate on purpose**, and the gap between them is the
product. An approved interest still shows the investor only the summary card.
Do not render "approved" as "you can now see the report" — until a reveal
happens, `GET .../reports/{run_id}` returns `404`.

`InterestResponse.revealed_run_ids` is the flag to branch on. Empty means
nothing has been opened; a run id in it means that report is readable.

### Investor endpoints

| | |
|---|---|
| `POST /v1/discover/{id}/interest` | Express interest. Idempotent — a repeat returns the original. `404` if the startup has not published. |
| `GET /v1/interests` | Your own, newest first. Optional `?status=`. |
| `GET /v1/interests/{id}/reports/{run_id}` | The full report, **only** if it was revealed to you. |

**The founder is never told an interest exists.** They hear about it when SACI
arranges the meeting. Do not build a founder-facing "someone viewed you" screen.

### SACI admin endpoints (web)

| | |
|---|---|
| `GET /v1/interests` | Every interest, **oldest first** — it is a work queue. |
| `POST /v1/admin/interests/{id}/approve` · `POST /v1/admin/interests/{id}/decline` | One decision per interest; `409` if already decided. |
| `POST /v1/admin/interests/{id}/reveal` | Opens the latest completed audit to that investor. `409` unless approved. |

Every one of those writes an immutable audit-log entry. A reveal names **who
opened what, for whom**.

### Statuses

| `status` | Means |
|---|---|
| `pending` | Waiting on SACI. |
| `approved` | SACI will broker it. **Not a reveal.** |
| `declined` | Terminal. |
| `withdrawn` | Terminal, set by the investor. |

### A reveal names a run, not a startup

A founder who re-audits produces a new report, and an investor shown the old one
has no claim on the new one. Always pass the `run_id` you were given —
`audit_run_id` on the reveal, or an entry in `revealed_run_ids`.

---

## 6. Enums

Every value the client may switch on. Treat unknown values as forward
compatibility, not as an error — parse defensively.

| Enum | Values |
|---|---|
| `Role` | `founder`, `investor`, `admin` |
| `AccountStatus` | `pending_verification`, `active`, `suspended` |
| `KycStatus` | `none`, `pending`, `verified`, `failed` |
| `SubscriptionStatus` | `none`, `active`, `past_due`, `canceled` |
| `Stage` | `idea`, `pre_seed`, `seed`, `series_a`, `series_b_plus`, `growth` |
| `DocumentKind` | `deck`, `financials`, `cap_table`, `other` |
| `DocumentStatus` | `pending`, `ready`, `rejected` |
| `ScanStatus` | `pending`, `clean`, `infected`, `skipped` |
| `FieldSource` | `founder`, `document`, `inferred` |
| `BenchmarkMetric` | `gross_margin_percent`, `runway_months`, `ltv_cac_ratio`, `cac_payback_months`, `run_rate_vs_trailing_percent` |
| `AuditStatus` | `queued`, `running`, `succeeded`, `failed` |

`FieldSource` matters for UI, and will matter more once extraction is wired
(T2.8). A profile field carries the source of its value:

- `founder` — they typed it. Authoritative; nothing overwrites it.
- `document` — read out of an upload. Arrives with a `confidence` (0–1) and a
  `citation` naming the document and the quoted span. **Treat below `0.5` as
  provisional** and let the founder confirm or correct it.
- `inferred` — derived rather than stated. Provisional and editable.

Nothing today returns `document`, because no pipeline runs yet. Building the UI
to handle it now is cheaper than retrofitting it when T2.8 lands.

---

## 7. Not built yet

**Do not code against these.** Listed so you can plan, not integrate. No paths
exist for any of them today.

| Area | Task | Affects |
|---|---|---|
| **The report itself.** Audits run and finish (§5a), but nothing returns the verdict, scores, or action plan yet — that needs the per-tier serializer | T2.7/T4.2 | Founder mobile |
| Document-driven audits. Uploads are stored but **not yet read by the audit**: today a run scores the profile fields only | T2.4a | Founder mobile |
| Golden-set harness — no verdict has been tuned against hand-scored companies, so treat early scores as provisional in the product sense too | T2.9 | Founder mobile |

When the audit does land, two rules will govern how you render it, and both are
enforced server-side rather than left to the client:

- **`insufficient_data` is an absence, not a failure.** It means the audit could
  not be run on what was submitted — never show it as "not fundable". The
  founder has not been assessed, and telling them otherwise is the failure the
  whole `sufficiency` model exists to prevent.
- **`provisional` must always be labelled.** A conclusion drawn from partial
  evidence is offered, but rendering it as a plain result overstates it.
| Readiness tasks, evidence upload, re-audit gate | T3.1, T3.5, T3.6 | Founder mobile |
| Stripe checkout and subscriptions | T3.3, T3.4 | Founder mobile |
| Founder AI chat | T3.7 | Founder mobile |
| Investor profile + KYC gate | T4.1 | Investor mobile |
| Investor discovery, summaries, analyst chat | T4.2–T4.4 | Investor mobile |
| Interest → SACI approval → meeting | T4.5 | All three |
| Full-report reveal (admin action, audit-logged) | T4.6 | Admin web |

Two contract rules that will shape those endpoints when they land, worth
knowing now:

- **Investors only ever receive summary-tier data.** This is enforced in the
  retrieval layer, not by hiding fields client-side. There is no request that
  returns a full report to an investor.
- **Only a SACI admin action reveals a full report**, and every reveal is
  written to an immutable audit log.

---

## 8. Known gaps

Honesty over polish — these are real and currently unresolved:

- **`POST /v1/auth/register` requires `first_name` and `last_name`.** The Expo
  client in `frontend/` does not send them, so mobile registration currently
  returns **422**. Restoring those two fields client-side fixes it.
- **`first_name` / `last_name` can be `null`** on `UserResponse` for accounts
  created before the columns existed, and for admins (who are provisioned, not
  registered). Handle null.
- **Email delivery is unverified.** Verification and reset emails are built and
  tested but have never been sent through a live provider (T1.2a), so the
  end-to-end verify/reset journey is unproven.
- **Document storage is unverified.** Signing is proven offline, but no byte has
  been written to a real bucket (T1.5). Treat the upload flow as
  interface-stable, behaviour-untested.

---

## Keeping this honest

`tests/unit/test_client_guide.py` asserts that every path and enum value named
here exists in the live OpenAPI spec. A rename that forgets this file fails CI.
It cannot check prose — if you find the narrative wrong, say so and it gets
fixed in the same change as the code, per `CLAUDE.md` §6.
