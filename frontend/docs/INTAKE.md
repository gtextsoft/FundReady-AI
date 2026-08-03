# Intake design — what the form should ask, and why

A proposal, written from the client side, for reconciling the onboarding form
with the Startup Profile field set. It is not a client decision to make alone:
about half of it is `backend/app/modules/intake/fields.py`, which is flagged
**provisional** in the backend's own task list pending the missing
`saci-audit-platform-backend-spec.md`.

Status: **proposal.** Nothing here is built. See `TASKS.md` F1.8.

---

## 1. The two rules that decide every question

**The model interprets; it never computes** (`DECISIONS.md` D9).
`audit/finance.py` derives gross margin, net burn, runway, margin-adjusted LTV,
LTV/CAC and CAC payback from raw figures. Every one of those is a *result*.
The form must therefore ask for **inputs**, never ratios.

**The rubric grades whether a claim is evidenced** (`audit/rubric/v1`). Two of
its criteria, verbatim:

> Market size is derived, not quoted as a single unsourced headline number.

> Revenue or usage is corroborated by a source other than the founder's own
> narrative.

Put together: **a field that asks for a conclusion manufactures the exact
answer the rubric marks down.** A box labelled "TAM ($B)" produces an unsourced
headline number, and `market_opportunity` then scores it poorly. Today's form
does this three times — `tam`, `margin`, `ltv`.

A third rule follows from the first two: **the form is not the only intake.**
Extraction (T2.4) fills fields from uploaded documents, and thin data yields a
`provisional` verdict by design rather than a false one. The form should carry
what documents will not reliably give — intent, structure, and the founder's
own account of their constraints — and let extraction do the rest.

---

## 2. What the audit actually scores

`rubric/v1` publishes eleven dimensions. Seven are shared; one is fundability
only; three are saleability only.

| Dimension | Scope | What it needs to see |
| --- | --- | --- |
| `financial_health` | both | Runway, margin consistent with the business model, burn **trending** |
| `unit_economics` | both | LTV/CAC and payback, or the specific missing input named; retention evidence |
| `traction` | both | Revenue corroborated externally; growth over a period long enough to beat one good month |
| `market_opportunity` | both | A bottom-up derivation reconcilable with any top-down figure; serviceable market |
| `team` | both | Roles filled **or named as gaps**; specific prior experience; time commitment |
| `legal_and_ip` | both | Entity identified, cap table coherent, IP assigned, licences held |
| `data_integrity` | both | Figures reconcile **across documents**; units, currency and dates line up |
| `scalability` | fundability | The constraint capital would relieve, named; deployment plan mapping to it |
| `owner_independence` | saleability | Relationships with the company not the individual; documented operations |
| `transferability` | saleability | Contracts survive change of control; company-held systems and accounts |
| `revenue_durability` | saleability | Recurring separated from one-off; concentration quantified; renewal behaviour |

**Saleability is half the product and the current form ignores it entirely.**
An investor asks whether capital accelerates the business; an acquirer asks
whether it still works after the founder leaves. Three dimensions exist only to
answer the second question and nothing in the form feeds them.

---

## 3. The field set

`source` is where a value should come from: **form** (the founder types it),
**doc** (extraction reads it), **derived** (`finance.py` computes it — never
stored, never asked).

### Already on the server and correctly shaped

| Field | Kind | Source | Feeds |
| --- | --- | --- | --- |
| `name`, `sector`, `stage`, `country`, `currency` | indexed columns | form | benchmark lookup, discovery |
| `description`, `business_model` | text | form | every dimension as context |
| `website` | text | form | corroboration |
| `founded_year` | year | form | stage sanity |
| `team_size`, `founder_count`, `founders_full_time` | integer | form | `team` |
| `monthly_revenue_minor`, `monthly_costs_minor`, `cash_on_hand_minor` | money_minor | form + doc | `financial_health` |
| `cost_of_revenue_minor` | money_minor | form + doc | gross margin |
| `last_12m_revenue_minor` | money_minor | doc | `traction` |
| `active_customers`, `monthly_active_users` | integer | form | `traction` |
| `customer_acquisition_cost_minor` | money_minor | form | `unit_economics` |
| `average_revenue_per_customer_minor` | money_minor | form | `unit_economics` |
| `monthly_churn_percent` | percent | form | `unit_economics` |
| `total_raised_minor`, `current_raise_target_minor` | money_minor | form | `scalability` |
| `cap_table_summary` | text | doc | `legal_and_ip` |
| `ip_owned`, `contracts_transferable` | boolean | form | `legal_and_ip`, `transferability` |
| `key_person_dependency` | text | form | `owner_independence` |

### Proposed additions to `fields.py`

Ordered by how much a dimension currently goes unscored without them.

| Proposed field | Kind | Source | Why |
| --- | --- | --- | --- |
| `capital_use` | text | form | **`scalability`'s central criterion** — "the constraint capital would relieve is named specifically". Nothing on the server holds it today, and it is the first question any investor asks. |
| `revenue_concentration_percent` | percent | form | `revenue_durability` requires concentration **quantified**. Share of revenue from the largest customer. Also the standard acquirer red flag. |
| `recurring_revenue_percent` | percent | form | `revenue_durability` — "recurring or contracted revenue is separated from one-off sales". Without it, MRR and one-off project income look identical. |
| `monthly_revenue_history` | text (JSON array) or a repeated `money_minor` | form + doc | `traction` needs a **trend**, and `financial_health` needs burn direction. A single MoM percentage cannot distinguish a trend from one good month — which is precisely what the criterion rules out. |
| `target_customer_count` | integer | form | Bottom-up market sizing, half of `customers x price`. |
| `target_price_minor` | money_minor | form | The other half. Together these are a *derivation* the rubric can reconcile — unlike a TAM headline. |
| `serviceable_geographies` | text | form | `market_opportunity` — "where the business can actually operate today, including regulatory and geographic limits". |
| `open_roles` | text | form | `team` — "the roles the plan requires are either filled **or named as gaps**". The current `technical: yes/no` is a thin proxy. |
| `founder_experience` | text | form | `team` — "relevant prior experience is specific and checkable". |
| `regulatory_licences` | text | form | `legal_and_ip` — licences the model requires, "or their absence is flagged". |
| `contract_length_months` | integer | form | `revenue_durability` — renewal behaviour. |

### A stage question, not a stage value

`Bootstrapped` is not a stage; it is a funding posture, and it is orthogonal to
`seed` or `series_a`. Adding it to the `Stage` enum would make two different
axes share one field and corrupt benchmark lookup, which is keyed on stage.

Either add `is_bootstrapped: boolean`, or drop the option — `total_raised_minor
= 0` already says it.

---

## 4. Changes to the form

### Stop asking

| Field | Replace with | Reason |
| --- | --- | --- |
| `margin` | `cost_of_revenue_minor` | Gross margin is `(revenue − cost of revenue) / revenue`, computed by `finance.py`. Asking for the result invites a number nobody can check. |
| `ltv` | `average_revenue_per_customer_minor` + `monthly_churn_percent` | LTV is computed **margin-adjusted**, deliberately: raw ARPU/churn overstates a low-margin business. A founder's own LTV will not match and the audit will have to disagree with them. |
| `tam` | `target_customer_count` + `target_price_minor` + `serviceable_geographies` | The rubric explicitly rejects an unsourced headline figure. |
| `growth` | `monthly_revenue_history` | A single percentage cannot show a trend. |
| `technical` | `open_roles` + `founder_experience` | The rubric wants gaps named, not a boolean. |
| `revModel` (MRR/ARR toggle) | keep, but as a unit hint only | It changes how `revenue` is interpreted, not what is stored. Store monthly minor units always. |

### Start asking

Everything in the additions table above. The ones that most change what the
audit can say: `capital_use`, `revenue_concentration_percent`,
`recurring_revenue_percent`, and the revenue history.

### Keep

`company`, `sector`, `location`, `year`, `stage`, `revenue`, `cac`, `founders`,
`deck` — all already map.

---

## 5. Sequencing

The form is four steps and already too long for `tam`-style vanity questions to
be earning their place. A shape that follows the dimensions:

1. **Identity** — name, sector, stage, country, founded year, description,
   business model, website
2. **Money** — monthly revenue, costs, cost of revenue, cash on hand, revenue
   history, total raised, raise target, **what the capital is for**
3. **Customers** — active customers, ARPU, churn, CAC, concentration, recurring
   share, contract length
4. **Team & ownership** — founder count, full-time, open roles, experience, IP
   assignment, contract transferability, key-person dependency, licences

Saleability questions sit in step 4 and cost the founder very little, which is
the argument for asking them at all: three whole dimensions currently score
`insufficient_data` for want of about six inputs.

---

## 6. Open questions for the backend

1. **Does `fields.py` grow, or does the form shrink?** The six unmapped answers
   are the visible symptom; the eleven proposed additions are the actual gap.
2. **How is a revenue history modelled?** A repeated field, a JSON array, or
   left entirely to extraction from financial documents.
3. **Is `Bootstrapped` a stage, a boolean, or nothing?**
4. **Which of these are document-only?** `cap_table_summary` and
   `last_12m_revenue_minor` are already effectively extraction-fed. Marking a
   field document-only keeps it out of the form and off the founder's plate.
5. **What is `data_integrity` scored against before any document exists?**
   Uploads are blocked on T1.5 (built, but no R2 buckets and no keys), so today
   that dimension has nothing to reconcile.
