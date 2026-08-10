# Skills reference

Design input for the audit engine and mentor posture. **Nothing here is
imported, executed, or shipped at runtime** — these are documents that informed
how the rubric, prompts, and mentor system text were written, kept in the repo
so a future reader can see where a criterion came from rather than guessing.

Source: the `claude-skills` collection, MIT licensed — see `LICENSE`.
Copyright (c) 2025 Alireza Rezvani, plus the individual skill authors credited
in each `SKILL.md`.

## Placement rule (do not reverse quietly)

| Path | Role |
| --- | --- |
| Repo-root `skills/` | Claude/Cursor **agent tooling** library (~188 packs). Stays at the monorepo root. |
| `backend/docs/skills-reference/` | **Curated, MIT-attributed subset** used as design reference only (ruff-excluded). |
| `backend/app/` | Runtime code. **Never** vendors or imports `SKILL.md` files. |

**Do not move the full root `skills/` tree into `backend/` or `app/`.** Shipping
advisor personas, investment-advisor scripts, or a conversational loop into
FastAPI would fight the audit design (schema-validated JSON out, no persona
loop) and risk DECISIONS.md D9 if financial formulas leak into prompts.

Mentor chat (T3.7) retrieves **live DB data** — the caller's `FounderReport`,
tasks, and profile facts — not these markdown files. Expand this folder only
with short substance notes (e.g. `mentor-grounding.md`); never with scripts or
full plugin trees.

## Why these eight, and not the other 180

The collection is largely **conversational advisor personas** — "ask the user,
gather context, work through it together". The FundReady audit engine is the
opposite shape: profile and documents in, schema-validated JSON out, nobody in
the loop. Copying a persona into an audit prompt would fight that design, so
what was taken is the *substance* — which questions a competent reviewer asks,
and what evidence they insist on — not the prose.

| Skill | Informed |
| --- | --- |
| `cfo-advisor` | `financial_health`, `unit_economics`, `scalability` |
| `cfo-review` | The scoring posture: numerate and skeptical, not encouraging |
| `gc-review` | `legal_and_ip` — IP assignment, cap table, regulatory exposure |
| `stress-test` | `data_integrity`, and the consistency check (T2.5) |
| `board-deck-builder` | Report narrative and bad-news delivery (T2.7) |
| `deep-research` | "Every source saved" — why web validation must be persisted |
| `dossier` | Hypothesis-tested company research: state the claim, then verify it |
| `market-research` | `market_opportunity` — top-down **and** bottom-up, never one unsourced number |
| `mentor-grounding.md` | Founder mentor posture: answer only from retrieved evidence (T3.7) |

## What was deliberately excluded

* **`business-investment-advisor`** — answers a different question (should I buy
  this equipment?) and puts ROI/NPV/IRR **formulas in the prompt** for the model
  to apply. That is a direct DECISIONS.md D9 violation; `audit/finance.py` owns
  every financial calculation.
* **`compliance-os/*`** — certification prep (ISO 27001, SOC 2, GDPR). Real
  work, but not what "fundable and saleable" asks.
* **`research/pulse`** — Reddit and Hacker News sentiment. Gameable by the
  subject of the audit, so it is weak evidence for a verdict.
* Every skill's `scripts/*.py` — they duplicate `audit/finance.py`.

## The one that got away

`saas-metrics-coach` (from the since-deleted `claude-skills-main`) was the
closest architectural match in either collection: it computed metrics in a
script rather than a prompt, benchmarked them against a reference keyed by
stage and segment, and labelled bands. Its `references/benchmarks.md` carried
the only real benchmark data — cited to OpenView, Bessemer, SaaS Capital, and
Paddle.

It was **not** seedable into `benchmarks` even when it existed: its bands are
stage-agnostic, and `audit.service.lookup_benchmark` matches stage exactly
precisely because "a seed-stage band tells you nothing about a growth-stage
company". Copying one band across six stages would assert exactly what that
rule denies. The table stays empty until SACI curates it, which is the correct
outcome — the admin CRUD from T2.3 exists for that.
