"""Background workers.

Long-running, token-heavy work (audits, evidence assessment) runs here, off the
request thread, as idempotent jobs that are safe to retry (DECISIONS.md D14).
Services enqueue; workers execute the pipeline.
"""
