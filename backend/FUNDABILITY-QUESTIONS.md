# Fundability onboarding — every step, every question, and what the AI does with each answer

**As of 2026-08-07.** Generated against the code, not against a spec. The
authorities are:

| Subject | File |
|---|---|
| The question set | `app/modules/intake/fields.py` |
| What is calculated in code | `app/modules/audit/finance.py` |
| What the AI grades against | `app/modules/audit/rubric/v1/__init__.py` |
| Cross-checks and integrity scoring | `app/modules/audit/consistency.py` |
| How scores become a verdict | `app/modules/audit/synthesis.py` |

If this document and those files disagree, they are right and this is stale.

This is the companion to `FOUNDER-ONBOARDING.md`. That document is the build
spec for the mobile developer — labels, types, endpoints, validation. **This one
answers a different question: for each thing we ask a founder, what does the AI
actually do with the answer, and what breaks if it is missing.** Every entry
below names the specific computation or the specific written criterion the
answer serves. Nothing is here because it seemed useful.

---

## Bottom line

- A founder answers **44 questions**: 5 identifying details plus 39 profile
  questions. **11 are required** before an audit can run.
- The AI never produces a financial number. Margins, burn, runway, LTV, LTV:CAC,
  CAC payback and the three-month revenue/cost trends are computed in
  `finance.py` and handed to the model as given. The model interprets them.
- Fundability is scored across **8 dimensions** (7 shared with saleability, plus
  Scalability). Saleability adds 3 more.
- An answer left blank is treated as **absent, not bad**. Absence caps the
  verdict rather than lowering the score — which is why skipping optional
  questions buys a weaker verdict, not a faster one.
- **Registration documents are read, not verified** (`DECISIONS.md` D7). A CAC
  certificate of incorporation, uploaded as `registration_certificate`, becomes
  corroboration for legal name and registration number — never a "verified"
  badge.

---

## Part 1 — The seven steps

| # | Step | Endpoint | What the AI gains from this step |
|---|---|---|---|
| 1 | Register | `POST /v1/auth/register` | Nothing directly. Establishes that a real person controls a real mailbox at a real domain, which is the weakest possible identity signal but the only one available before documents exist. |
| 2 | Verify email | `POST /v1/auth/verify-email` | Proves mailbox control. The account is `pending_verification` and can do nothing until the link is clicked. |
| 3 | Log in | `POST /v1/auth/login` | Nothing. Issues the token every later step needs. |
| 4 | Create the startup profile | `POST /v1/startups` | The 5 identifying details. `sector`, `stage` and `country` are the **benchmark lookup key** — without them the AI has no peer group and must reason from first principles at lower confidence. |
| 5 | Answer the profile questions | `PATCH /v1/startups/{profile_id}` | The evidence base. Partial saves are expected; `missing_fields` in the response says what is outstanding. |
| 6 | Request the audit | `POST /v1/startups/{startup_id}/audits` | `202` queued, `200` if an identical audit already exists, `422` if a required answer is missing. The `422` is a **pre-spend gate**: scoring an incomplete profile would burn the audit budget to produce "insufficient data", an answer the founder can have for free. |
| 7 | Poll for the result | `GET /v1/startups/{startup_id}/audits/{run_id}` | Statuses `queued`, `running`, `succeeded`, `failed`. |

Documents (pitch deck, financials, cap table, **registration certificate**) can
be uploaded at `POST /v1/startups/{startup_id}/documents`. The AI reads figures
out of them to fill gaps and to **corroborate** what the founder claimed. This
is the only way to satisfy the criteria that require a source other than the
founder's own narrative. Use `kind: registration_certificate` for a CAC (or
equivalent) certificate of incorporation.

`GET /v1/registries` returns the country → registrar map the registration form
should use. **Key on ISO alpha-2** (`NG`), not display names (`"Nigeria"`).

### Registration gates, and what they do not prove

| Rule | Applies to | Error code |
|---|---|---|
| Company email required | Founders only | `consumer_email_domain` |
| No disposable inboxes | Everyone, all roles | `disposable_email_domain` |

The second rule is stricter on purpose: a throwaway inbox has no password, so
anyone who knows the address can read the verification link and every future
password-reset link. That is account takeover by design, so it applies to
investors too.

**Neither rule verifies a company exists.** Anyone can buy a domain. Company
name is pre-filled from the domain (`founder@kanmipay.com` → "Kanmipay") purely
to save typing; it is often slightly wrong and must stay editable.

---

## Part 2 — What happens to the answers

Once the audit runs, the answers pass through six stages
(`app/modules/audit/pipeline.py`):

1. **Extraction** — uploaded documents are read for the same profile fields.
   The reader is instructed to report only what a document *states*: never
   infer, estimate, average, or calculate. Every extracted value carries a
   citation and a confidence, and is tagged `source: document` so it is never
   confused with the founder's own claim.
2. **Consistency check** — the founder's figures are cross-checked against each
   other and against the documents. Produces findings and a
   `data_integrity_score` out of 100.
3. **Finance** — every ratio is computed here, in code. No model involved.
4. **Rubric scoring** — the model scores each in-scope dimension 0–100 against
   written criteria, citing what each score rests on.
5. **Synthesis** — scores become verdicts by a fixed rule, plus a report and an
   action plan.
6. **Persistence** — the `AuditRun` is stored with its `rubric_version` so a past
   audit stays explainable.

Two rules govern the whole pipeline and are worth stating in any founder-facing
copy:

- **Money is arithmetic, not opinion.** The model never produces a financial
  figure.
- **Absent is not bad.** A missing figure is `insufficient_data`. A figure that
  is present and poor is a low score. The pipeline keeps these separate all the
  way to the verdict, because collapsing them produces a false result.

---

## Part 3 — The 5 identifying details

All five required. They are indexed columns rather than questionnaire fields
because investor discovery filters on them later.

### `name` — "What is your business called?"
Text, max 200. Pre-filled from the email domain, editable.

**How it helps the AI:** it does not score anything. It is the label on the
report and the thing consistency checking uses to notice when a document belongs
to a different entity.

### `sector` — "What sector are you in?"
**Free text**, max 120. Deliberately not a dropdown — the platform must accept
sectors that do not exist yet, and the rubric's adaptive layer handles novelty.

**How it helps the AI:** first key in the benchmark lookup
(*sector × stage × metric × region*). It is also what makes the Financial health
criterion *"gross margin is consistent with the business model described"*
gradeable at all — a services business showing software margins is only a
finding if the AI knows it is a services business.

**Skipped:** cannot be. Required.

### `stage` — "What stage are you at?"
Enum: `idea`, `pre_seed`, `seed`, `series_a`, `series_b_plus`, `growth`.

**How it helps the AI:** matched **exactly** in benchmark lookup. A wrong stage
means no peer comparison at all, and the model then has to reason from first
principles and lower its confidence. It also sets what "good" means — a runway
or margin that is normal at pre-seed is a concern at Series A.

### `country` — "Where is the business registered?"
ISO 3166-1 alpha-2, uppercased.

**How it helps the AI:** the region key in benchmark lookup, with fallbacks
(`exact` → `region_fallback` → `sector_fallback` → `broad`). It also bounds the
Market opportunity criterion *"the serviceable market reflects where the
business can actually operate today, including regulatory and geographic
limits"*.

### `currency` — "What currency do you report in?"
ISO 4217, e.g. `NGN`, `USD`, `GBP`.

**How it helps the AI:** everything is computed in the profile's own declared
currency — there is no FX conversion, deliberately, because every ratio that
drives scoring is dimensionless (a 62% margin means the same thing in any
currency). The code does need this to know the **minor-unit exponent**: yen has
no decimal places, dinars have three. Getting it wrong makes the same integer
wrong by a factor of 100, and a benchmark comparison off by 100× looks like a
real finding.

---

## Part 4 — The 27 profile questions

`REQ` marks the six that block an audit. For each question: what it asks, what
the AI does with it, and what it costs to leave blank.

### Business

#### `description` — REQ — "What does your business do?"
Text, in the founder's own words.

**How it helps the AI:** it is the frame for every other judgement. Nearly every
criterion is relative to what the business claims to be — Financial health asks
whether gross margin is *"consistent with the business model described"*,
Scalability asks whether growth *"depends on a step change the business has
never demonstrated"*. Neither question exists without this answer. It also
contributes narrative evidence to Market opportunity.

**Skipped:** cannot be. The audit will not start.

#### `business_model` — REQ — "How do you make money?"
Text — subscription, marketplace, licence, and so on.

**How it helps the AI:** primary narrative input to **Scalability**, which asks
whether more capital would produce more output or just more cost. It is also
what makes a margin interpretable: the same 40% gross margin is weak for
software and strong for logistics, and only this answer tells the AI which
comparison to make.

**Skipped:** cannot be.

#### `website` — "Website, if you have one"
Text.

**How it helps the AI:** **nothing, today.** Recorded for human reviewers. No
dimension reads it and the audit does not fetch it.

#### `founded_year` — "What year did you start trading?"
Year, 1800–2100.

**How it helps the AI:** cross-checked against `incorporation_year`. If the
company was incorporated *after* trading started, consistency raises
`incorporated_after_trading` at `likely` severity — sole traders who later
incorporate are common, so the wording leaves room for the founder to be right.
Without `incorporation_year`, this field still feeds nothing scored.

---

### Legal entity (T1.6)

Self-reported. A uploaded `registration_certificate` is how these become
corroborated rather than asserted. Separate from the `name` column, which D20
says is a domain-derived prefill and nothing downstream may treat as a legal
name.

#### `legal_name` — "Registered legal name, exactly as on your certificate"
Text.

**How it helps the AI:** carries the **Legal and IP** criterion *the operating
entity is identified and the cap table is coherent*. When the same name appears
on an uploaded certificate, rule 4 of the scoring prompt (corroboration beats
assertion) kicks in and the score rests on stronger evidence.

**Skipped:** Legal and IP has only `cap_table_summary` / `ip_owned` / contracts
to go on for entity identity.

#### `registration_number` — "Registration number"
Text. Label and placeholder come from `GET /v1/registries` for the profile's
country (`RC number` / `RC 1234567` for Nigeria). **Never validated against a
format** — rejecting a real number over a regex mismatch is worse than accepting
an unusual one.

**How it helps the AI:** specific enough to be checked against a certificate
citation. Feeds Legal and IP alongside `legal_name`.

#### `registrar` — "Registered with"
Text. Prefill from `GET /v1/registries` (`CAC` for `NG`, `Companies House` for
`GB`, …). Editable.

**How it helps the AI:** context for Legal and IP; names which body's document
would corroborate the number.

#### `incorporation_year` — "What year was the company incorporated?"
Year, 1800–2100. Extraction pulls a four-digit year out of a stated date on a
certificate (`"12 March 2019"` → `2019`).

**How it helps the AI:** cross-checked against `founded_year` (see above). Also
bounds how long the entity has existed for Team / Legal judgements.

#### `regulatory_licences` — "What licences or permissions does this business need, and do you hold them?"
Text.

**How it helps the AI:** the **Legal and IP** criterion *licences or regulatory
permissions the business model requires are held, or their absence is flagged*,
and Transferability's *licences and permissions are transferable or
reobtainable*.

---

### Market and growth

These four exist for a specific reason. Until they were added on 2026-08-03,
`market_opportunity` and `scalability` were being graded against criteria
**nothing on the form asked for**. Both routinely came back unevidenced — and
because a verdict needs every in-scope dimension evidenced to read `ready` or
`not_yet`, a founder could answer everything else perfectly and still be capped
at `provisional`.

All four are optional, on the principle that an audit which refuses to start is
worse than one that starts and says which answers would sharpen it.

#### `market_size_note` — "How big is the market you can actually serve today, and how did you work that out?"
Text.

**How it helps the AI:** carries three of the four **Market opportunity**
criteria at once:

- *market size is derived, not quoted as a single unsourced headline number*
- *a bottom-up derivation (customers × price) is present and is reconcilable
  with any top-down figure given*
- *the serviceable market reflects where the business can actually operate
  today, including regulatory and geographic limits*

**The label is load-bearing.** One question must elicit a number, how it was
derived, and what bounds it. Placeholder text should show a worked example:
*"12,000 registered pharmacies in Lagos × ₦5,000/month = ₦60m/month. We can't
serve other states yet — each needs its own council registration."* A founder
who writes "huge" scores nothing, because "huge" is not derived.

**Skipped:** Market opportunity has only `description` to go on and will likely
return `insufficient_data`, which caps the verdict at `provisional`.

#### `competition_note` — "Who else solves this problem for your customers today?"
Text.

**How it helps the AI:** the fourth Market opportunity criterion —
*competition is identified specifically enough to be checked*. "Specifically
enough to be checked" is the whole bar: named competitors can be verified, "no
real competitors" cannot and reads as a gap in the founder's knowledge rather
than an empty market.

#### `growth_constraint` — "What is limiting your growth right now, and what have you already proven you can do about it?"
Text.

**How it helps the AI:** the first **Scalability** criterion — *the constraint
capital would relieve is named specifically* — and it feeds the fourth,
*growth does not depend on a step change the business has never demonstrated*.
The second half of the label ("what have you already proven") is what makes that
fourth criterion gradeable.

#### `use_of_funds` — "If you raised money, what would it buy?"
Text.

**How it helps the AI:** the third Scalability criterion — *the plan for
deploying new capital maps to that constraint*. This is graded **against**
`growth_constraint`, which is why the two are separate questions. Naming a
bottleneck and saying what money would buy are different claims, and the rubric
checks whether the second answers the first. Asking them as one question
destroys the check.

#### `delivery_cost_trend` — "As you have grown, has the cost to serve one more customer gone up, down, or stayed flat?"
Text.

**How it helps the AI:** the **Scalability** criterion *delivery cost per
additional customer is falling, flat, or rising — and which it is, is
evidenced*. Without it Scalability has the constraint and the use of funds but
not the delivery-cost direction.

---

### Team

#### `team_size` — REQ — "How many people work on this, including founders?"
Integer, ≥ 0.

**How it helps the AI:** context for the **Team** criterion *the roles the plan
requires are either filled or named as gaps* — a plan needing ten roles at a
team of two is a finding. It is also a **consistency denominator**: churn that
looks like a decimal-point error is judged against customer count, and team
arithmetic is cross-checked below.

**Skipped:** cannot be.

#### `founder_count` — "How many founders?"
Integer. Must be ≤ `team_size`.

**How it helps the AI:** with `founders_full_time`, gives the Team criterion
*founder time commitment is stated*.

**Cross-check:** more founders than total team is impossible. It raises the
`more_founders_than_team` finding at `certain` severity, costing **25 integrity
points**. Worth validating client-side so the founder fixes a typo instead of
being penalised for it.

#### `founders_full_time` — "How many founders work on this full time?"
Integer. Must be ≤ `founder_count`.

**How it helps the AI:** directly answers *founder time commitment is stated*.
Part-time founders are not disqualifying, but undisclosed part-time founders are
the kind of thing an investor finds later, so the rubric wants it stated. Also
feeds **Owner independence** on the saleability side.

**Cross-check:** more full-time founders than founders raises
`more_full_time_than_founders` — again `certain`, again 25 points.

#### `founder_experience` — "What have the founders done before that is relevant to this?"
Text.

**How it helps the AI:** the **Team** criterion *relevant prior experience is
specific and checkable, not self-described seniority*. "Serial entrepreneur"
scores nothing; "built and sold a Lagos last-mile firm with 40 vans" can be
checked.

---

### Money — the required core

All amounts are **integer minor units**. This is the single most common source
of wrong answers: `450000000` for ₦4,500,000, never `4500000.00` and never
`"₦4.5m"`.

Every figure below is raw input. **No ratio is ever stored** — they are
recomputed in `finance.py` on every run, which is what makes the same input
produce the same score.

#### `monthly_revenue_minor` — REQ — "Revenue in your most recent full month"
Money, minor units.

**How it helps the AI:** the most load-bearing single number in the profile. It
is an input to five computed figures:

| Computed | Formula | Also needs |
|---|---|---|
| `gross_margin_percent` | `(revenue − cost of revenue) / revenue × 100` | `cost_of_revenue_minor` |
| `net_burn_minor` | `costs − revenue` (positive = burning) | `monthly_costs_minor` |
| `annual_run_rate_minor` | `revenue × 12` | — |
| `run_rate_vs_trailing_percent` | `(revenue × 12 − trailing) / trailing × 100` | `last_12m_revenue_minor` |
| `is_profitable` | `revenue ≥ costs` | `monthly_costs_minor` |

It then feeds **Financial health**, **Traction**, and **Data integrity** (it is
the anchor every scale cross-check is measured against).

**Note on zero:** zero revenue is a legitimate answer and is handled
deliberately. Gross margin returns *unavailable, reason `no_revenue`* rather
than 0%, because "a pre-revenue company has no margin" is a different statement
from "its margin is nothing" and the rubric must be able to tell them apart.

#### `monthly_costs_minor` — REQ — "Total operating costs that month"
Money, minor units.

**How it helps the AI:** with revenue it gives **net burn**; with cash it gives
**runway**. These two carry the Financial health question *"can this business
fund its own operations, and for how long?"* almost by themselves. Also sets
`is_profitable`.

**Cross-check:** operating costs ten times revenue or more raises
`cost_exceeds_revenue_implausibly`. The threshold is 10×, not 2×, on purpose — a
false positive costs more than a missed subtlety, because the founder stops
believing the audit.

#### `cash_on_hand_minor` — REQ — "Cash available right now"
Money, minor units.

**How it helps the AI:** the numerator of **runway** — `cash / net burn`. Runway
is the first Financial health criterion (*runway is stated and supported by the
submitted figures, or is explicitly unknowable*) and one of the five benchmarked
metrics.

**Note:** a business that is not burning gets *no runway figure* — reason
`not_burning`, not infinity. Reporting a very large number would let the rubric
score it as an exceptionally long runway, when the correct reading is that
runway is the wrong question for a profitable business.

#### `cost_of_revenue_minor` — "Direct cost of delivering that revenue"
Money, minor units.

**How it helps the AI:** the only input to **gross margin** other than revenue —
and gross margin is the gateway to half the financial picture. Without it, three
further figures are unavailable, because all three are margin-adjusted:

- `gross_margin_percent`
- `ltv_minor` — `(ARPU × gross margin) / churn`
- `cac_payback_months` — `CAC / (ARPU × gross margin)`
- `ltv_cac_ratio` — depends on LTV, so it falls too

**Skipped:** this one blank takes out most of Unit economics as well as a
Financial health criterion and a benchmarked metric. Of all the optional money
fields, this is the most expensive to omit.

#### `last_12m_revenue_minor` — "Revenue over the last 12 months"
Money, minor units.

**How it helps the AI:** the only thing standing between the audit and a single
frozen month. It produces `run_rate_vs_trailing_percent` — the latest month
annualised, compared against the last year's actual.

**Read the name literally: this is not a growth rate.** A growth rate needs a
monthly time series. What this compares is where the business is *now* against
where it has *been*: positive is suggestive of growth without measuring it. The
three-month fields below are what fully closes the Traction growth criterion.

#### `monthly_revenue_3m_ago_minor` — "Revenue three months ago"
Money, minor units.

**How it helps the AI:** with the latest month, produces
`revenue_change_3m_percent` — a real growth rate over a named period, computed
in code. Closes Traction's *growth is shown over a period long enough to
distinguish a trend from a single good month*. Without it the audit sees one
frozen month and cannot tell a business growing 20% a month from one shrinking
at the same rate.

#### `monthly_costs_3m_ago_minor` — "Total costs three months ago"
Money, minor units.

**How it helps the AI:** produces `costs_change_3m_percent`. Closes Financial
health's *burn is trending in a direction the founder can account for*.

#### `monthly_marketing_spend_minor` — "What do you spend a month winning customers?"
Money, minor units.

**How it helps the AI:** Unit economics criteria *acquisition cost includes the
sales and marketing effort actually used, not only paid media* and *a strong
ratio is checked against simply under-investing in growth*.

---

### Traction and customers

These five together produce LTV, LTV:CAC and CAC payback. Skip them and the
Unit economics dimension — 20 of fundability's 115 weight, the joint-heaviest —
has nothing to score.

#### `active_customers` — "How many paying customers today?"
Integer.

**How it helps the AI:** the denominator of the strongest **consistency**
cross-check in the system. Revenue is compared against
`customers × ARPU`; a discrepancy of 10× or more raises
`revenue_vs_customers`. It is also what makes the churn plausibility check
work — *0.02% monthly churn at 50,000 customers is ten people a month, a real
measurable number; at 34 customers it is 0.0068 of a person*. Range alone cannot
distinguish those, which is exactly why the check lives here and not at the
field boundary. Feeds Traction and Revenue durability.

#### `monthly_active_users` — "Monthly active users, if you track it"
Integer.

**How it helps the AI:** contributes to the Traction criterion *revenue or usage
is corroborated*. Usage is the fallback signal for a business whose revenue is
still thin, and the gap between users and paying customers is itself
informative.

#### `customer_acquisition_cost_minor` — "What does it cost to win one customer?"
Money, minor units.

**How it helps the AI:** the denominator of **LTV:CAC** and the numerator of
**CAC payback**, both benchmarked metrics. The investor convention the code
notes as healthy is a ratio of 3 or above.

**Note:** a CAC of zero yields *no ratio*, reason `no_acquisition_cost` — which
is either genuine organic growth or, more often, a CAC nobody has measured. The
AI is told to treat those as different things and not to score the second as the
first.

**Known limit:** the Unit economics criterion *acquisition cost includes the
sales and marketing effort actually used, not only paid media* cannot be checked
today, because nothing asks what the founder counted. See Part 7.

#### `average_revenue_per_customer_minor` — "Average revenue per customer per month"
Money, minor units.

**How it helps the AI:** input to **LTV**, **CAC payback**, and the
`revenue_vs_customers` consistency check. Feeds Unit economics and Revenue
durability.

#### `monthly_churn_percent` — "What share of customers do you lose each month?"
Percent, **0–100 — not a fraction**.

**How it helps the AI:** the divisor in LTV. It also carries the Unit economics
criterion *retention or churn evidence supports the lifetime assumed*.

**This is the most consequential validation rule on the form.** `0.02` meaning
2% is indistinguishable from a genuine 0.02% by range alone, and getting it
wrong inflates lifetime value by roughly **100×** — which then inflates LTV:CAC,
which then produces a confident and completely wrong Unit economics score. Two
defences exist: the field rejects anything outside 0–100, and the consistency
stage flags churn below 0.1% by weighing it against customer count. The form
should stop it before either fires. Label the input with a `%` suffix.

**Note:** zero churn yields *no LTV*, reason `no_churn`. At zero the formula
diverges, which in practice means the input is wrong or the history is too
short — not that customers are worth infinitely much.

#### `pilot_or_lou_count` — "How many pilots or letters of intent that are not paying yet?"
Integer.

**How it helps the AI:** Traction criterion *pilots, letters of intent, and
paying customers are distinguished from one another rather than counted
together*. Without it, `active_customers` alone cannot tell the difference.

#### `largest_customer_revenue_share_percent` — "What share of revenue comes from your biggest customer?"
Percent, 0–100.

**How it helps the AI:** Revenue durability criterion *customer concentration is
quantified* — a first-order funding risk, not only a sale risk. 40% from one
customer is a finding investors ask about.

---

### Funding

#### `total_raised_minor` — "How much have you raised to date?"
Money, minor units. **Context only.**

#### `current_raise_target_minor` — "How much are you raising now?"
Money, minor units. **Context only.**

**How these help the AI:** "context only" means the audit reads them but no
dimension is scored on them alone. How much a founder *wants* is not evidence
that capital would produce output rather than cost. They become meaningful next
to `use_of_funds`, which says what the money buys — so ask both or neither.

#### `cap_table_summary` — "Who owns what, in summary?"
Text.

**How it helps the AI:** the **Legal and IP** criterion *the operating entity is
identified and the cap table is coherent*. "Coherent" is the bar: percentages
that do not reconcile, or an entity that is not the one trading, are findings a
reader can check.

---

### Saleability — and why they matter to funding too

The platform audits whether a business is fundable **and** saleable. These three
carry most of the second question, but two of them feed shared dimensions and so
affect the funding verdict as well.

#### `ip_owned` — "Does the business own its core intellectual property?"
Boolean — real `true`/`false`, not `"yes"` and not `1`.

**How it helps the AI:** the **Legal and IP** criterion *IP created by founders,
employees, and contractors is assigned to the company*. Legal and IP is a shared
dimension, so this affects the fundability verdict directly. A company that does
not own what it sells is not a funding candidate, whatever its margins look
like. Also feeds Transferability.

#### `contracts_transferable` — "Would customer contracts survive a change of ownership?"
Boolean.

**How it helps the AI:** the **Transferability** criterion *contracts survive a
change of control, or the ones that do not are identified*, plus Legal and IP's
*material contracts and any encumbrances on them are disclosed*.

#### `key_person_dependency` — "What breaks if one specific person leaves?"
**Text, not a boolean.** A boolean is rejected.

**How it helps the AI:** the **Team** criterion *key-person risk is identified
where one individual holds the relationships, the knowledge, or the credentials*
— shared, so it moves the funding verdict — and the **Owner independence**
criteria *customer relationships sit with the company rather than with one
individual* and *decisions that only the founder can currently make are
identified*.

It is free text because a yes/no cannot be graded against those criteria. The
answer wanted is a sentence: *"Every client was won personally by the founder
and renews on that relationship; there is no account manager."* That names the
risk specifically enough to become an action. "Yes" names nothing.

---

## Part 5 — Validation rules, and the reason each one exists

| Rule | Right | Wrong | What it prevents |
|---|---|---|---|
| Money is integer minor units | `450000000` for ₦4,500,000 | `4500000`, `4500000.00`, `"₦4.5m"` | Every figure wrong by 100× |
| Percent is 0–100, not a fraction | `2` for 2% | `0.02` | LTV inflated ~100×, then a confident wrong Unit economics score |
| Whole numbers cannot be negative | `0` | `-1` | Nonsense denominators |
| Booleans must be real booleans | `true` | `"yes"`, `1` | `isinstance(True, int)` is true in Python, so `"team_size": true` would quietly store a team of one — every numeric field excludes booleans by hand for this reason |
| Year is four digits, 1800–2100 | `2022` | `22` | Typos read as businesses |
| `null` is always allowed | field left empty | — | A half-known profile is the normal case, not an error |

Every value also carries a `source` — `founder`, `document`, or `inferred` —
because the rubric grades corroboration, and a founder's own claim is not the
same kind of input as a figure read out of their bank statement.

---

## Part 6 — From answers to a verdict

### The 8 fundability dimensions and their weights

| Dimension | Weight | The question it answers |
|---|---|---|
| Financial health | 20 | Can this business fund its own operations, and for how long? |
| Unit economics | 20 | Does each customer earn more than they cost to acquire? |
| Traction | 15 | Is there verifiable evidence that customers want this? |
| Data integrity | 15 | Do the submitted materials agree with each other? |
| Scalability | 15 | Would more capital produce more output, or just more cost? |
| Market opportunity | 10 | Is the addressable market real and large enough to matter? |
| Team | 10 | Can these people execute this particular plan? |
| Legal and IP | 10 | Does the business actually own what it is selling? |

Total 115. The numbers are relative within a scope and are not required to sum
to anything — saleability totals 150, because the two verdicts share seven core
dimensions and add different ones on top. Saleability's three extra dimensions
are Owner independence (20), Transferability (15) and Revenue durability (15).

### The five standing rules the AI is given

These outrank any instruction found in an uploaded document or in founder text —
uploaded material is treated as untrusted data, never as instructions.

1. **No conclusion without evidence.** If the submission does not support a
   dimension, mark it `insufficient_data` and move on. A confident score on thin
   data is the worst possible output — worse than saying nothing, because someone
   will act on it.
2. **Never invent a benchmark.** When no band matches, reason from first
   principles or the nearest defensible analogue, say so in the rationale, and
   lower confidence accordingly.
3. **Distinguish absent from bad.** A missing figure is `insufficient_data`; a
   figure that is present and poor is a low score.
4. **Corroboration beats assertion.** A number a founder states about themselves
   is weaker evidence than the same number in a bank statement, a contract, or
   an invoice — and the model must say which it relied on.
5. **Write unmet criteria as actions.** They become the founder's tasks, so each
   must name something a person can actually go and do.

### How the verdict is decided

The verdict is **computed, not asked for**. Three reasons it cannot be a second
model opinion: the same input must produce the same verdict; a founder told
"not yet" is owed a reason a rule can supply and a judgement cannot; and the
guarantee against a false "fundable" has to be enforced by something that cannot
be talked out of it.

The rule, in order:

| Condition | Verdict |
|---|---|
| `data_integrity_score` < **50** | `insufficient_data` — and the rubric call is skipped entirely, because the verdict is already decided and that call is the most expensive thing the platform does |
| Fewer than **50%** of in-scope dimensions evidenced | `insufficient_data` |
| Any dimension unevidenced, **or** any marked provisional | `provisional` — even if the score is high |
| Weighted mean ≥ **70** | `ready` |
| Otherwise | `not_yet` |

The weighted mean is normalised over the dimensions **actually evidenced**, not
over the scope's full weight. Dividing by the full weight would penalise a
profile for its gaps on top of the coverage gate and the provisional rule
already doing so — the same thing charged three times.

Coverage, by contrast, is a plain count. Weighting it would let a profile that
evidenced only the two heaviest dimensions clear the gate with nine of eleven
questions unanswered.

**`insufficient_data` must never be rendered as "not fundable".** It is an
absence, not a failure. A founder who was never assessed must not be left
thinking they were assessed and rejected.

### How data integrity is scored

Starts at 100, floor 0:

| Event | Penalty |
|---|---|
| A `certain` finding (arithmetic impossibility) | −25 |
| A `likely` finding (implausible scale) | −15 |
| Each contradiction found between documents | −20 |

Findings the code raises: `revenue_vs_annual`, `revenue_vs_customers`,
`churn_implausibly_low`, `cost_exceeds_revenue_implausibly`,
`more_founders_than_team`, `more_full_time_than_founders`,
`incorporated_after_trading`, `contradiction`.

Two `certain` findings and one contradiction put a profile below the floor and
end the audit with no verdict. Both `certain` findings are team-arithmetic
typos, which is the argument for validating them client-side.

The contradiction checker is instructed that different periods, different
precision, and gaps are **not** contradictions, and to assume a mistake rather
than deception.

### What the founder gets back

Each dimension returns a score, a sufficiency, a rationale that says what would
raise it, and `unmet_criteria`. Those criteria become readiness tasks, ordered
worst-scoring dimension first. Whether a task is `required` or `recommended` is
computed from the same threshold as the verdict, not chosen: a dimension that
could not be scored at all is `required` (it trips the provisional rule, and no
strength elsewhere clears that), a dimension below 70 is `required`, and one at
or above 70 is `recommended` — the boundary sits on the passing side in both
places.

The first live run produced **44 action items**. They were specific and correct,
and no founder reads 44 — so five dimensions contribute one priority item each
to a short list. Nothing is dropped: every item stays in the response and the
client can offer "show everything".

Evidence uploaded against a task is graded against that task's exact criterion.
"They uploaded something" is not a pass; when the grader is unsure it returns
`needs_more`, not `pass`. There is a cap of **3 graded attempts** per task,
because grading is a model call, a model does not answer identically twice, and
the outcome decides entry to investor visibility — unlimited attempts means a
determined founder eventually passes anything. Reaching the cap **locks** the
task rather than failing it: a `fail` is a statement about the work, a lock is a
statement about the process, and telling a founder their business fell short
when they merely ran out of tries would conflate the two. Only a SACI admin can
reopen it, and that is audit-logged.

---

## Part 7 — What the questions still cannot tell the AI

T1.6 closed the Tier 1 fundability gaps and Legal and IP's licences criterion.
What remains is almost entirely **saleability**, plus one Traction criterion no
question can close.

### Tier 2 — saleability. Ask when the readiness loop is the product surface.

| Field | Type | Suggested label | Criterion it closes |
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

### The criteria no question can close

Traction requires that *revenue or usage is corroborated by a source other than
the founder's own narrative*, and that *named customers or contracts are
evidenced, not just listed*. Asking a founder to assert it harder corroborates
nothing. This is what **document upload** is for — financials, invoices, signed
contracts. A registration certificate corroborates the entity; it does not
corroborate revenue.

Rule 4 still requires the model to say when a score rests on self-reported
figures alone.

### How to stage the additions without wrecking the form

44 questions is not a form anybody finishes. Recommended shape:

1. **Required core (11).** Blocks the audit. Keep exactly as it is.
2. **"Improve your score"** — market-and-growth, legal entity, and the Tier 1
   fundability fields, presented *after* the first audit returns and targeted
   at the dimensions that actually came back thin. The verdict already reports
   `unevidenced_dimensions`, so the app can ask only the questions that would
   change *this* founder's result.
3. **Tier 2** alongside the readiness-task flow, where a founder is already
   working through improvements.

Point 2 is the important one: **the audit tells you which questions to ask
next.** Nothing needs to be asked speculatively.

---

## Appendix — The required 11, as a checklist

An audit will not start until all eleven are present. `missing_fields` in the
`PATCH` and `422` responses lists exactly which are outstanding; render it as a
checklist.

| # | Field | Where |
|---|---|---|
| 1 | `name` | column |
| 2 | `sector` | column |
| 3 | `stage` | column |
| 4 | `country` | column |
| 5 | `currency` | column |
| 6 | `description` | profile |
| 7 | `business_model` | profile |
| 8 | `team_size` | profile |
| 9 | `monthly_revenue_minor` | profile |
| 10 | `monthly_costs_minor` | profile |
| 11 | `cash_on_hand_minor` | profile |

Six of the eleven are the minimum that lets `finance.py` compute anything at
all: revenue, costs and cash produce burn, runway, run rate and profitability,
and `description` plus `business_model` are what make those numbers
interpretable rather than merely present.
