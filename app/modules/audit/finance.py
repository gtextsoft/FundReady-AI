"""Deterministic financial computation for the audit engine.

**INVARIANT (DECISIONS.md D9):** every financial figure the platform reports --
margins, burn, runway, CAC/LTV, growth rates, currency normalisation -- is
computed *here, in code*. The LLM interprets these numbers; it never produces
them. Never move a calculation into a prompt, and never accept a computed
figure from model output as ground truth.

Money is handled as integer minor units with an ISO 4217 currency code
(AGENTS.md section 4). Ratios are exact where the inputs allow it.
"""
