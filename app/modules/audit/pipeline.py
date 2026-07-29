"""Audit stage orchestration.

Runs on the background worker, never inline in a request (DECISIONS.md D14).
`audit.service` enqueues the job; `app.workers.tasks` invokes this pipeline.

Stages (ARCHITECTURE.md section 4):
  1. extraction        -- documents to Startup Profile fields, with source and
                          confidence per field, plus missing-field flags
  2. consistency check -- cross-document contradictions to a dataIntegrityScore
  3. finance           -- `finance.py`, in code, no LLM (DECISIONS.md D9)
  4. rubric scoring    -- versioned rubric via `app.ai`, structured output only
  5. synthesis         -- verdicts, founder report, action plan
  6. persistence       -- AuditRun (with rubricVersion) plus embeddings

The whole pipeline must be idempotent and safe to retry.
"""
