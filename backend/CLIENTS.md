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

If you omit `name` on profile creation it is derived from your company email
domain — `founder@acme.com` → `Acme`. That is a starting point, not a verified
company name; send `name` explicitly to control it.

### Admin only (web) — 403 until MFA is enrolled

| | |
|---|---|
| `POST /v1/admin/users` | Provision another admin |
| `POST /v1/admin/users/{id}/suspend` · `/reactivate` | Suspension bumps `session_valid_after`, killing live sessions |
| `PATCH /v1/admin/users/{id}/role` | Change a role |
| `GET /v1/benchmarks` · `GET /v1/benchmarks/{id}` | Browse and read the benchmark KB |
| `POST /v1/benchmarks` · `PATCH /v1/benchmarks/{id}` · `POST /v1/benchmarks/{id}/retire` | Create, revise, retire |

**All five benchmark endpoints are admin-only, including the reads.** Two
reasons, and the second is easy to miss: a founder who could *write* benchmarks
could move the goalposts they are judged against, and a founder who could
merely *read* them would know exactly what to claim. The guard lives in the
service layer, so the route signature alone does not show it — the endpoint
descriptions do.

> **Note for the admin web app:** benchmarks are *retired*, never deleted. An
> audit cites what it scored against, so the row must survive.

---

## 5. Document upload (three steps)

Files never pass through this API — they go straight to object storage.

```
1. POST /v1/startups/{id}/documents   → 201 UploadTicket { upload_url, document_id, ... }
2. PUT  <upload_url>                  → direct to storage. Send the EXACT
                                        content_type you declared in step 1.
3. POST /v1/documents/{id}/complete   → 201 confirms and starts scanning
```

Three things that will bite you:

- **The declared `content_type` is pinned into the signature.** Uploading with
  a different one fails at the storage layer, not here.
- **Size is checked after the fact.** A presigned PUT cannot enforce a size
  limit, so an oversized file uploads successfully and is then deleted
  server-side. Check the size client-side before starting.
- **The allowlist constrains what you *declare*, not the bytes.** Real content
  inspection happens in the scanner. `scan_status` starts `pending` and a
  document is not trustworthy until it is `clean`.

Downloads are the mirror image: `GET /v1/documents/{id}/download` returns a
short-lived signed URL, not the bytes.

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

`FieldSource` matters for UI: a value marked `inferred` was derived, not stated
by the founder, and should be shown as provisional and editable.

---

## 7. Not built yet

**Do not code against these.** Listed so you can plan, not integrate. No paths
exist for any of them today.

| Area | Task | Affects |
|---|---|---|
| Audit engine (extraction, scoring, reports) | T2.4–T2.9 | Founder mobile |
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
