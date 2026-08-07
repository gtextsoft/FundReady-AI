from pathlib import Path

p = Path("FUNDABILITY-QUESTIONS.md")
text = p.read_text(encoding="utf-8")
start = text.index("## Part 7 — What the questions still cannot tell the AI")
end = text.index("## Appendix — The required 11, as a checklist")
new = """## Part 7 — What the questions still cannot tell the AI

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

"""
p.write_text(text[:start] + new + text[end:], encoding="utf-8")
print("replaced part 7")
