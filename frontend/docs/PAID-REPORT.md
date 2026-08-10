# Country, currency, and the paid detailed report

A proposal. **Nothing here is built yet.**

Covers two asks: knowing which country a founder is in so we can adapt currency
and payment method, and charging the local equivalent of $17 for a detailed
report that explains, step by step, how to become more fundable.

---

## 1. The constraint that decides the design

**Apple and Google require their own in-app purchase for digital goods consumed
inside the app, and take 15–30%.**

A detailed report unlocked inside the app is exactly that. It is not a physical
good, not a service delivered elsewhere, and not a marketplace transaction —
it is the clearest possible case of what their rules cover. A card checkout
through Stripe or Paystack inside the iOS app **will be rejected at review**.

This matters more than usual here because of the price. At $17, Apple's cut is
around $2.55 to $5.10. And in-app purchase does not let you charge "the local
equivalent of $17" — you pick a **price tier**, and Apple sets what that costs
in each country, on their FX, with their rounding.

There are three honest ways out, and the choice shapes everything else:

| Option | How it works | Cost |
| --- | --- | --- |
| **Use in-app purchase** | Apple/Google price tiers, their currencies | 15–30%, and you lose control of the exact local price |
| **Sell it outside the app** | Buy on the web, the app just unlocks what the account already owns | Keeps 100% minus card fees, keeps exact pricing. Cannot link to the web page from inside iOS — Apple forbids steering |
| **Ship Android and web only** | No App Store, no rules | Rules out iPhone, which is where you were heading |

The middle option is what most B2B products do. It is also the reason many
apps have a "your subscription is managed on the website" screen.

**This decision should be made before any of the rest is built**, because it
determines whether the app contains a payment flow at all.

---

## 2. Country: what we already have, and what is missing

The onboarding form asks for headquarters, and it already resolves to a country
and a currency — twelve are mapped: NG, GH, KE, ZA, GB, US, CA, IN, SG, DE, NL,
AE. Money is stored in minor units against the ISO currency code, so a price in
naira or rupees needs no new machinery.

Two gaps:

**The company's country is not necessarily the payer's country.** A Nigerian
founder living in London pays with a UK card. For tax and for choosing a
payment processor, what matters is where the *card* is, not where the company
is registered. These should be two separate pieces of information.

**Investors have no country at all.** Only founders fill in a profile. If
investors ever pay for anything, that needs solving separately.

---

## 3. Payment method has to vary by country, and already does

From the PRD: **Stripe does not onboard Nigeria-registered businesses.** Nigeria
is served through Paystack. So this is not a future concern — it is true for the
largest market on the list.

Practically that means at least two processors, chosen by the payer's country:

- **Paystack** for Nigeria, Ghana, Kenya, South Africa — local cards, bank
  transfer, USSD, mobile money. Card-only would exclude a lot of real customers.
- **Stripe** for UK, US, EU, and the rest.

The app should never decide which one. It should ask the server "how does this
person pay?" and render whatever comes back.

---

## 4. Pricing $17 in local money

**Never convert on the device.** Three reasons: the client must not decide what
something costs, live rates make the price flicker between screens, and a stale
rate on an old app version quietly undercharges.

Two ways to do it server-side:

**Live FX at checkout.** Always exactly $17. Produces prices like ₦26,432.17,
which look unconsidered, and changes daily.

**Fixed local prices, reviewed periodically.** ₦25,000. £13. ₹1,400. A round
number that reads as a real price, with someone deciding when to move it.
Drifts from exactly $17 as rates move, which is normally fine.

The second is what almost every product does, and it is what I would suggest.
Either way the server returns a ready-formatted amount plus the raw minor units,
and the app displays it without arithmetic.

One detail already handled: **zero-decimal currencies.** Yen has no minor unit,
so multiplying by 100 would overstate a price a hundredfold. The existing money
mapping knows this.

---

## 5. What "the detailed report" actually is

Most of this already exists in the backend's plan, which is good news — the new
part is the paywall, not the content.

- **T2.7** produces the founder report and action plan
- **T3.1** turns audit gaps into required and recommended tasks, specific to
  that audit
- **T2.6** scores each dimension with explicit criteria and citations

A step-by-step guide to becoming more fundable is essentially the action plan,
ordered by impact. The pieces are specified; none of them are built yet.

### This settles an open question, and someone should notice

`backend/TASKS.md` carries an unresolved item: *"Confirm founder report
visibility (full actionable audit vs summary)."*

This feature answers it — **free gives the verdict and the headline gaps; $17
gives the detailed reasoning and the step-by-step plan.** That is a real product
decision being made, and it should be recorded as one rather than arriving
implicitly through a payment feature.

### And it collides with the existing paywall

The app already has a **$149 one-off unlock** (`domain/pricing.ts`) covering
dealflow listing, the AI mentor, investor introductions and the programmes.
There is also a founder subscription in the backend plan (T3.4).

That makes three ways to pay. Someone needs to say how they relate:

- Is $17 a cheaper first step that the $149 later replaces?
- Does the $149 include the detailed report?
- Does a subscriber get it free?

Left unanswered, a founder will pay $17 and then be asked for $149 for
something they reasonably thought they had bought.

---

## 6. What the backend needs to provide

Four things. None of them exist today.

1. **The payer's country and currency on the user record.** Separate from the
   company's country. There is no country field on the user at all right now.

2. **A price endpoint.** Given the user, return the amount in their currency, as
   both a formatted string and minor units, plus which processor to use. The app
   renders it and never calculates.

3. **A purchase, verified server-side.** Whatever the rail, entitlement is
   granted on the processor's word — a webhook — never on the client saying it
   paid. The existing subscription design already works this way and this should
   match it.

4. **An entitlement flag on the account,** so the app can ask "does this person
   have the detailed report?" without inspecting payment history. `/v1/users/me`
   already carries `subscription_status`; this belongs beside it.

---

## 7. What the app does once those exist

Small, and mostly already in place:

- Show the price the server returns, on the results screen behind the verdict
- Hand off to the checkout the server names
- Re-read entitlement afterwards from the server, never assume success
- Render the detailed report and the ordered action plan
- Show the free version as genuinely useful, not as a crippled teaser

The existing paywall screen is the right pattern and the entitlement gates in
`domain/access.ts` already work this way — they read state from the server and
never let the client decide it has paid.

---

## 8. Questions to settle first

1. **In-app purchase, or sell it on the web?** Decide this before anything else
   is built. It determines whether the app contains a checkout at all.
2. **How do $17, $149 and the subscription relate?**
3. **Fixed local prices, or live FX?**
4. **Does the free version show the score?** A verdict with no reasoning may
   read as withholding rather than as a sample.
5. **Refunds.** A report is delivered instantly and cannot be returned. Worth a
   stated policy before the first request, not after.
