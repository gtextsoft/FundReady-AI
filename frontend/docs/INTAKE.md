# What the sign-up form should ask, and why

A proposal. **Nothing here is built yet.**

Half of it needs the backend, because that is where answers are stored. See
`TASKS.md` F1.8.

---

## The problem in one paragraph

The form asks a founder 15 questions. Six of those answers have nowhere to be
stored, so they are thrown away. The app tells the founder they were not saved,
which is honest but is not a fix. Looking at it properly, the six missing boxes
turned out to be the smaller half of the problem.

---

## 1. Some questions ask the founder to do our homework

We ask things like *what is your profit margin* and *what is a customer worth
to you*.

We do not need to ask. If a founder gives us their revenue and their costs, the
system works the margin out itself — correctly, and the same way for every
company. It already does this.

Asking is worse than unnecessary. The audit checks whether a number is **backed
by something**. A figure a founder typed into a box has nothing behind it, so it
scores badly. By asking, we hand them a way to lose marks.

The market size question is the clearest case. The scoring rules say, in as many
words, that a single unsourced headline number counts against you — and a box
labelled "TAM ($B)" produces exactly that.

**These four questions should go:**

| Question we ask now | Ask this instead | Why |
| --- | --- | --- |
| Gross margin % | Cost of revenue | Margin is revenue minus cost of revenue. We can do that sum. |
| Customer lifetime value | Average revenue per customer, and monthly churn | We calculate this in a specific way. A founder's own figure will not match ours, and then the audit has to publicly disagree with them. |
| Market size (TAM) | How many customers they are going after, and their price | Two real numbers we can check beat one big number we cannot. |
| Growth % | The last few months of revenue | See point 3. |

---

## 2. We are not asking the things that matter most

**We never ask what the money is for.** A founder says they want to raise
£500k and we do not ask what for. It is the first question any investor asks,
the audit is meant to grade it, and there is nowhere to put the answer.

**We ask almost nothing about selling the business.** The product promises two
verdicts: *can you raise money*, and *could someone buy this*. Nearly every
question we ask serves the first. The things a buyer always checks — how much of
your revenue comes from one customer, how much of it repeats versus one-off
sales, whether contracts survive a change of owner — we barely ask.

That is three whole sections of the audit scoring "we could not tell", for want
of about six questions that cost the founder a minute.

---

## 3. One question is the wrong shape

We ask for a growth percentage. One number.

The audit wants to know whether growth is **real or one lucky month**. A single
number cannot answer that. A few months of revenue figures can.

The same figures also show whether spending is going up or down, which the audit
also asks about. One change, two problems solved.

---

## 4. What to add

Ordered by how much is currently missing without them.

| Add | What it means | Why it matters |
| --- | --- | --- |
| `capital_use` | What the money is for | The single biggest gap. Investors ask first; we never ask. |
| `revenue_concentration_percent` | Share of revenue from the biggest customer | A buyer's first red flag. Lose that customer, lose the business. |
| `recurring_revenue_percent` | How much repeats vs one-off | Repeating revenue is worth far more. Right now the two look identical to us. |
| `monthly_revenue_history` | Revenue for the last few months | Shows a trend rather than a snapshot. Replaces the growth % question. |
| `target_customer_count` | How many customers they are going after | Half of an honest market size. |
| `target_price_minor` | What they charge | The other half. |
| `serviceable_geographies` | Where they can actually operate today | Being allowed to trade somewhere is not the same as wanting to. |
| `open_roles` | Which jobs are unfilled | We currently ask only "is a founder technical, yes or no". Naming the gaps is more useful and more honest. |
| `founder_experience` | Relevant background | "Ten years in payments" is checkable. "Experienced" is not. |
| `regulatory_licences` | Licences the business needs | Missing a required licence is a serious finding. Nothing surfaces it. |
| `contract_length_months` | Typical contract length | Tells a buyer whether revenue sticks around. |

## A note on "Bootstrapped"

The form offers it as a stage, alongside Seed and Series A. It is not a stage —
it means *has not raised money*, which is a different thing entirely. A company
can be bootstrapped and at any stage.

Storing it as a stage would also quietly break comparisons, because we compare
companies against others at the same stage. Either store it as its own yes/no,
or drop it — "total raised = 0" already says it.

---

## 5. What stays exactly as it is

Company name, sector, location, founding year, stage, revenue, customer
acquisition cost, number of founders, and the deck upload. All of these already
work and already have somewhere to go.

---

## 6. A form that flows better

Four steps, grouped so each one feels like a single topic:

1. **About the company** — name, sector, stage, country, year founded, what you
   do, how you make money, website
2. **Money** — revenue, costs, cost of revenue, cash in the bank, the last few
   months of revenue, raised so far, how much you want, **and what it is for**
3. **Customers** — how many, what they pay, how many leave, what it costs to win
   one, biggest customer share, how much repeats, contract length
4. **Team and ownership** — founders, who is full time, unfilled roles,
   background, who owns the intellectual property, whether contracts transfer,
   what only the founder can do, licences held

Step 4 is short and mostly yes/no, which is the argument for asking at all:
three sections of the audit currently score nothing for want of about a minute
of the founder's time.

---

## 7. Questions for the backend

1. **Does the storage grow, or does the form shrink?** The six thrown-away
   answers are the visible symptom. The eleven additions above are the real gap.
2. **How should a few months of revenue be stored?** A list, or read out of the
   financial documents instead.
3. **Is "Bootstrapped" a stage, a yes/no, or nothing?**
4. **Which answers should come from documents rather than the form?** Anything
   read out of an upload should not also be typed.
5. **What is the "do the numbers add up" check scored against before uploads
   work?** Document upload is built but has never stored a file — no storage
   account is configured — so that part of the audit currently has nothing to
   compare.
