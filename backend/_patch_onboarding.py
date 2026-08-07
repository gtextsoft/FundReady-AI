from pathlib import Path

p = Path("FOUNDER-ONBOARDING.md")
text = p.read_text(encoding="utf-8")
start = text.index("## What is still missing, and what to ask next")
# Keep "For the mobile developer" section that follows
end = text.index("## For the mobile developer")
new = """## What is still missing, and what to ask next

T1.6 closed Tier 1 fundability and the Legal and IP licences gap. What remains
is almost entirely **saleability**. See `FUNDABILITY-QUESTIONS.md` Part 7 for
the Tier 2 list and the staging recommendation: keep the required 11 as the
audit gate, ask the rest after the first audit against `unevidenced_dimensions`.

None of the Tier 2 saleability questions below is built yet.

| Field | Type | Suggested label | Closes |
|---|---|---|---|
| `recurring_revenue_percent` | percent | "What share of revenue is recurring or contracted?" | Revenue durability |
| `typical_contract_months` | integer | "How long is a typical customer contract?" | Revenue durability |
| `channel_dependency` | text | "Does your revenue depend on one channel, platform or partner?" | Revenue durability |
| `operations_documented` | boolean | "Could someone else run day-to-day operations from written process?" | Owner independence |
| `founder_salary_minor` | money | "What do the founders pay themselves a month?" | Owner independence |
| `systems_in_company_name` | boolean | "Are bank accounts, domains and software subscriptions in the company's name?" | Transferability |
| `supplier_dependencies` | text | "Which suppliers or platforms would hurt most to lose?" | Transferability |
| `hiring_gaps` | text | "What roles do you still need to fill?" | Team |
| `material_contracts_note` | text | "Any major contracts, loans or obligations we should know about?" | Legal and IP |

### Not solvable by a question

Traction asks that revenue is corroborated by a source other than the founder's
own narrative. Asking harder does not corroborate anything — that is what
document upload is for.

---

"""
p.write_text(text[:start] + new + text[end:], encoding="utf-8")
print("updated FOUNDER-ONBOARDING missing section")
