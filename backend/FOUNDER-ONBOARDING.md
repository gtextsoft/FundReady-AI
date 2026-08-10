# Founder onboarding — every question the AI audit uses

**As of 2026-08-03.** Generated against `app/modules/intake/fields.py`, which is
the single source of truth. If this document and the code disagree, the code is
right and this is stale.

Two audiences: the mobile developer building the screens, and anyone who needs
to explain what the audit actually asks a founder for.

---

## Bottom line

A founder answers **32 questions in total** — 5 identifying details plus 27
profile questions, of which **11 are required** before an audit can run.
Everything else is optional, but almost every optional question feeds a specific
part of the score, so skipping them buys a weaker verdict rather than a faster
one.

**Four questions are new as of 2026-08-03**, and they closed the worst gap in
the form: two of the eleven things the AI grades previously had *no question
behind them at all*, which capped almost every real audit at *provisional*.

**17 grading criteria still have no question behind them.** The full list — each
with the exact criterion it would close, and a recommended order — is at the end
of this document. That is the answer to "what else should we be asking founders".

---

## The journey, end to end

| # | Step | Endpoint | Notes |
|---|---|---|---|
| 1 | Register | `POST /v1/auth/register` | Company email required for founders. Two rejection rules below. |
| 2 | Verify the email | `POST /v1/auth/verify-email` | Account is `pending_verification` and cannot do anything until the emailed link is clicked. |
| 3 | Log in | `POST /v1/auth/login` | Returns the token everything after this needs. |
| 4 | Create the startup profile | `POST /v1/startups` | The 5 identifying details. Company name is pre-filled from the email domain. |
| 5 | Answer the profile questions | `PATCH /v1/startups/{profile_id}` | Partial saves are fine and expected. `missing_fields` in the response says what is still outstanding. |
| 6 | Request the audit | `POST /v1/startups/{startup_id}/audits` | `202` if queued, `200` if an identical audit already exists, `422` if anything required is missing. |
| 7 | Poll for the result | `GET /v1/startups/{startup_id}/audits/{run_id}` | Statuses: `queued`, `running`, `succeeded`, `failed`. |

Documents (pitch deck, financials) can be uploaded at
`POST /v1/startups/{startup_id}/documents` and the AI will read figures out of
them to fill gaps. **This is not live yet** — file storage is unprovisioned.

---

## Step 1 — who is allowed to register

Two separate rules, with different scopes and different messages. Show the exact
message the API returns; do not invent your own.

| Rule | Applies to | Trigger | Error code |
|---|---|---|---|
| **Company email** | Founders only | Gmail, Yahoo, Outlook, iCloud, Proton and ~30 others | `consumer_email_domain` |
| **No throwaway inboxes** | **Everyone**, all roles | Mailinator, YOPmail, 10MinuteMail, Guerrilla Mail and ~35 others, including their subdomains | `disposable_email_domain` |

The second rule is stricter on purpose. A Mailinator inbox has no password —
anyone who knows the address can read it, which means they can read the
verification link and every future password-reset link. That is account takeover
by design, so it applies to investors too, not just founders.

Investors *may* register with a personal address: an angel investing their own
money has no company domain.

**Neither rule verifies that a company exists.** Anyone can buy a domain. What
is actually verified is that the person controls the mailbox, which is what step
2 proves.

**Company name is guessed from the domain** — `founder@kanmipay.com` pre-fills
"Kanmipay". It is a prefill to save typing, it is often slightly wrong, and the
founder must be able to edit it.

---

## Step 4 — the 5 identifying details

All five are required. They are indexed columns, not part of the questionnaire
document, because investor discovery filters on them later.

| Field | Type | Notes |
|---|---|---|
| `name` | text | Pre-filled from the email domain; editable. |
| `sector` | **free text** | Deliberately not a dropdown — the platform must accept sectors that do not exist yet. |
| `stage` | enum | `idea`, `pre_seed`, `seed`, `series_a`, `series_b_plus`, `growth` |
| `country` | text | ISO country code. |
| `currency` | text | ISO 4217, e.g. `NGN`, `USD`, `GBP`. |

`stage` is matched **exactly** when looking up peer benchmarks, so a wrong stage
means no peer comparison at all.

---

## Step 5 — the 23 profile questions

`REQ` means an audit cannot run without it. Everything else is optional and
improves the score's confidence. The last column is what the answer actually
feeds — this is the honest answer to "why are you asking me this?"

### Business

| | Field | Type | Suggested label | Feeds |
|---|---|---|---|---|
| **REQ** | `description` | text | "What does your business do?" | Market opportunity *(narrative only)* |
| **REQ** | `business_model` | text | "How do you make money?" | Scalability *(narrative only)* |
| | `website` | text | "Website, if you have one" | **nothing** |
| | `founded_year` | year | "What year did you start trading?" | **nothing** |

### Market and growth — **new, added 2026-08-03**

These four exist because `market_opportunity` and `scalability` were being
graded against criteria **nothing on the form asked for**. Both dimensions
routinely came back "no evidence", and a verdict needs every in-scope dimension
evidenced to read `ready` or `not_yet` — so a founder could answer everything
else perfectly and still be capped at *provisional*.

All four are optional. An audit that refuses to start is worse than one that
starts and says which answers would sharpen it.

| | Field | Type | Suggested label | Feeds |
|---|---|---|---|---|
| | `market_size_note` | text | "How big is the market you can actually serve today, and how did you work that out?" | Market opportunity |
| | `competition_note` | text | "Who else solves this problem for your customers today?" | Market opportunity |
| | `growth_constraint` | text | "What is limiting your growth right now, and what have you already proven you can do about it?" | Scalability |
| | `use_of_funds` | text | "If you raised money, what would it buy?" | Scalability |

> **The labels are load-bearing.** `market_size_note` is one question that must
> elicit three things — a number, how it was derived, and what bounds it today
> (regulatory, geographic). Placeholder text should show a worked example:
> *"12,000 registered pharmacies in Lagos × ₦5,000/month = ₦60m/month. We can't
> serve other states yet — each needs its own council registration."* A founder
> who writes "huge" scores nothing.
>
> `growth_constraint` and `use_of_funds` are deliberately separate. Naming the
> bottleneck and saying what money would buy are different claims, and the
> rubric grades whether the second maps onto the first.

### Team

| | Field | Type | Suggested label | Feeds |
|---|---|---|---|---|
| **REQ** | `team_size` | integer | "How many people work on this, including founders?" | Team, Owner independence |
| | `founder_count` | integer | "How many founders?" | Team |
| | `founders_full_time` | integer | "How many founders work on this full time?" | Team, Owner independence |

Two impossibilities are rejected outright and cost the founder integrity points:
more founders than total team members, and more full-time founders than
founders. Both are certainties, not guesses — worth validating client-side too.

### Money — the required core

All amounts are **integer minor units**. See the validation section; this is the
single most common source of wrong answers.

| | Field | Type | Suggested label | Feeds |
|---|---|---|---|---|
| **REQ** | `monthly_revenue_minor` | money | "Revenue in your most recent full month" | Financial health, Traction, Data integrity |
| **REQ** | `monthly_costs_minor` | money | "Total operating costs that month" | Financial health, Data integrity |
| **REQ** | `cash_on_hand_minor` | money | "Cash available right now" | Financial health, Data integrity |
| | `cost_of_revenue_minor` | money | "Direct cost of delivering that revenue" | Financial health |
| | `last_12m_revenue_minor` | money | "Revenue over the last 12 months" | Traction |

Revenue and costs together give burn; with cash they give runway. Cost of
revenue gives gross margin. Trailing 12-month revenue is what lets the audit
distinguish a trend from one good month.

### Traction and customers

| | Field | Type | Suggested label | Feeds |
|---|---|---|---|---|
| | `active_customers` | integer | "How many paying customers today?" | Unit economics, Traction, Revenue durability |
| | `monthly_active_users` | integer | "Monthly active users, if you track it" | Traction |
| | `customer_acquisition_cost_minor` | money | "What does it cost to win one customer?" | Unit economics |
| | `average_revenue_per_customer_minor` | money | "Average revenue per customer per month" | Unit economics, Revenue durability |
| | `monthly_churn_percent` | percent | "What share of customers do you lose each month?" | Unit economics, Revenue durability |

These five together produce LTV, LTV:CAC and CAC payback. Skipping them means
the unit-economics dimension has nothing to score.

### Funding

| | Field | Type | Suggested label | Feeds |
|---|---|---|---|---|
| | `total_raised_minor` | money | "How much have you raised to date?" | context only |
| | `current_raise_target_minor` | money | "How much are you raising now?" | context only |
| | `cap_table_summary` | text | "Who owns what, in summary?" | Legal and IP |

"Context only" means the audit reads them but no dimension is scored on them
alone. How much a founder wants is not evidence that capital would produce
output rather than cost — it becomes meaningful next to `use_of_funds`, which
says what the money buys. Ask both or neither.

### Saleability

The platform audits whether a business is **fundable *and* saleable**. These
three carry most of the second question.

| | Field | Type | Suggested label | Feeds |
|---|---|---|---|---|
| | `ip_owned` | boolean | "Does the business own its core intellectual property?" | Legal and IP, Transferability |
| | `contracts_transferable` | boolean | "Would customer contracts survive a change of ownership?" | Legal and IP, Transferability |
| | `key_person_dependency` | **text** | "What breaks if one specific person leaves?" | Team, Owner independence |

> `key_person_dependency` is **free text, not a yes/no**. It expects a sentence
> such as *"Every client was won personally by the founder and renews on that
> relationship; there is no account manager."* A boolean is rejected.

---

## Validation rules that catch people out

| Rule | Right | Wrong |
|---|---|---|
| **Money is integer minor units** — kobo, cents, pence | `450000000` for ₦4,500,000 | `4500000`, `4500000.00`, `"₦4.5m"` |
| **Percent is 0–100, not a fraction** | `2` for 2% | `0.02` |
| **Whole numbers cannot be negative** | `0` | `-1` |
| **Booleans must be real booleans** | `true` | `"yes"`, `1` |
| **Year is four digits, 1800–2100** | `2022` | `22` |
| **`null` is always allowed** | field left empty | — |

The percent rule matters more than it looks. `0.02` meaning 2% is
indistinguishable from a genuine 0.02%, and it inflates customer lifetime value
by roughly 100×. The audit cross-checks churn against the customer count to
catch it, but the form should stop it first.

---

## Step 6 — the gate before an audit runs

An audit will not start until all **11** required answers are present: the 5
identifying details plus `description`, `business_model`, `team_size`,
`monthly_revenue_minor`, `monthly_costs_minor`, `cash_on_hand_minor`.

Missing any of them returns:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "...",
    "details": { "field": "missing_fields", "missing_fields": ["team_size", "..."] }
  }
}
```

This is a `422` **before anything is spent**. Scoring an incomplete profile
would burn the audit budget to produce "insufficient data" — an answer the
founder can have for free, with the list of what to fill in. Render
`missing_fields` as a checklist.

---

## What the AI does with the answers

Every answer is scored against **11 dimensions**, each with explicit written
criteria. Seven apply to both verdicts; one is fundability-only; three are
saleability-only.

| Dimension | Asks | Scope |
|---|---|---|
| Financial health | Can it fund its own operations, and for how long? | both |
| Unit economics | Does each customer earn more than they cost? | both |
| Traction | Is there verifiable evidence customers want this? | both |
| Market opportunity | Is the market real and big enough to matter? | both |
| Team | Can these people execute this plan? | both |
| Legal and IP | Does the business own what it sells? | both |
| Data integrity | Do the submitted figures agree with each other? | both |
| Scalability | Would more capital produce more output, or just more cost? | fundability |
| Owner independence | Does this still work once the founder leaves? | saleability |
| Transferability | Can what makes it valuable change hands? | saleability |
| Revenue durability | Will the revenue still be there next year? | saleability |

Two guarantees worth stating in any founder-facing copy:

- **Every financial figure is calculated in code, never by the AI.** Margins,
  burn, runway, LTV, CAC payback are arithmetic. The AI interprets them; it does
  not produce them.
- **Thin data never produces a confident verdict.** The four possible outcomes
  are `ready`, `not_yet`, `provisional`, and `insufficient_data`. The last one
  is an *absence*, not a failure, and must never be shown as "not fundable" — a
  founder who was never assessed must not think they were assessed and rejected.

---

## What is still missing, and what to ask next

The four market-and-growth questions above closed the worst gap. Mapping the
remaining questions against the rubric's written criteria shows **17 criteria
still have no question behind them.** Each row below names the exact criterion
it would close — nothing here is speculative, and nothing is proposed that
feeds no dimension.

None of these is built. This is the list to choose from.

### Tier 1 — fundability. Ask these next.

Eight questions, covering every remaining fundability gap. This is the set that
moves "can we reliably tell if a business is fundable" from *no* to *yes*.

| Field | Type | Suggested label | Closes |
|---|---|---|---|
| `monthly_revenue_3m_ago_minor` | money | "Revenue three months ago" | Traction: *growth shown over a period long enough to distinguish a trend from one good month* |
| `monthly_costs_3m_ago_minor` | money | "Total costs three months ago" | Financial health: *burn is trending in a direction the founder can account for* |
| `monthly_marketing_spend_minor` | money | "What do you spend a month winning customers?" | Unit economics: *acquisition cost includes the sales and marketing effort actually used, not only paid media*; and *a strong ratio is checked against simply under-investing in growth* |
| `largest_customer_revenue_share_percent` | percent | "What share of revenue comes from your biggest customer?" | Revenue durability: *customer concentration is quantified* — and it is a first-order funding risk, not only a sale risk |
| `pilot_or_lou_count` | integer | "How many pilots or letters of intent that are not paying yet?" | Traction: *pilots, letters of intent and paying customers are distinguished rather than counted together* |
| `delivery_cost_trend` | text | "As you have grown, has the cost to serve one more customer gone up, down, or stayed flat?" | Scalability: *delivery cost per additional customer is falling, flat, or rising — and which it is, is evidenced* |
| `founder_experience` | text | "What have the founders done before that is relevant to this?" | Team: *relevant prior experience is specific and checkable, not self-described seniority* |
| `regulatory_licences` | text | "What licences or permissions does this business need, and do you hold them?" | Legal and IP: *licences the business model requires are held, or their absence is flagged* |

The two `_3m_ago` figures are the highest-value pair in the table. They are the
only way the audit can see a *direction* — today it sees a single frozen month
and cannot tell a business growing 20% a month from one shrinking at the same
rate. They are also arithmetic, so the trend is computed in code rather than
judged by the model.

### Tier 2 — saleability. Ask these when the readiness loop is built.

The platform's promise is fundable **and** saleable, and the saleability half is
currently the thinner of the two.

| Field | Type | Suggested label | Closes |
|---|---|---|---|
| `recurring_revenue_percent` | percent | "What share of revenue is recurring or contracted?" | Revenue durability: *recurring revenue separated from one-off sales* |
| `typical_contract_months` | integer | "How long is a typical customer contract?" | Revenue durability: *contract lengths and renewal behaviour are evidenced* |
| `channel_dependency` | text | "Does your revenue depend on one channel, platform or partner?" | Revenue durability: *revenue dependent on a single channel or counterparty is identified* |
| `operations_documented` | boolean | "Could someone else run day-to-day operations from written process?" | Owner independence: *operations are documented well enough for a successor* |
| `founder_salary_minor` | money | "What do the founders pay themselves a month?" | Owner independence: *owner compensation below market is disclosed, since it flatters the margins a buyer would inherit* |
| `systems_in_company_name` | boolean | "Are bank accounts, domains and software subscriptions in the company's name?" | Transferability: *systems, accounts and data are held by the company, not personal accounts* |
| `supplier_dependencies` | text | "Which suppliers or platforms would hurt most to lose?" | Transferability: *supplier and platform dependencies are named* |
| `hiring_gaps` | text | "What roles do you still need to fill?" | Team: *the roles the plan requires are either filled or named as gaps* |
| `material_contracts_note` | text | "Any major contracts, loans or obligations we should know about?" | Legal and IP: *material contracts and any encumbrances are disclosed* |

### Not solvable by a question

One criterion cannot be closed this way. Traction asks that *revenue is
corroborated by a source other than the founder's own narrative*, and *named
customers or contracts are evidenced, not just listed*. Asking a founder to
assert it harder does not corroborate anything — this is what **document upload**
is for, and it stays open until file storage is provisioned.

### How to stage it without wrecking the form

23 questions is already long; 40 would be abandoned. Recommended shape:

1. **Required core (11).** Blocks the audit. Keep it exactly as it is.
2. **"Improve your score" (the 4 new + tier 1).** Present *after* the first
   audit returns, targeted at the dimensions that actually came back thin —
   the audit already reports `unevidenced_dimensions`, so the app can ask only
   the questions that would change this founder's result. That turns a long form
   into a short, obviously-worthwhile follow-up.
3. **Tier 2** alongside the readiness-task flow in Phase 3, where a founder is
   already working through improvements.

Point 2 is the important one: **the audit tells you which questions to ask**.
Nothing needs to be asked speculatively.

---

## For the mobile developer

- **Save partially and often.** `PATCH` accepts any subset; a half-known profile
  is the normal case, not an error. Use `missing_fields` from the response to
  drive a progress indicator.
- **Money inputs should show major units and send minor units.** Let the founder
  type `4,500,000` and multiply by 100 before sending. Never send a decimal.
- **Percent inputs should be labelled with a `%` suffix** so nobody types `0.02`.
- **`sector` is free text**, not a picker. A combobox with suggestions is fine;
  a closed list is not.
- **Known live bug:** registration currently returns `422` for every mobile
  sign-up. The backend has required `first_name` and `last_name` since
  2026-07-30 and the client does not send them. Restoring those two fields in
  `signUp` fixes it.
