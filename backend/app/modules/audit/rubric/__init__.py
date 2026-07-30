"""Versioned rubric definitions.

**Rubric versions are immutable (DECISIONS.md D12).** A published version is
never edited in place -- changes ship as a new `vN` package so that past
`AuditRun`s stay explainable. Every AuditRun records the `rubricVersion` it was
scored against.

Structure (DECISIONS.md D11): a universal core applying to every business, plus
an adaptive layer for sector-specific judgement. Where no benchmark exists for a
novel sector, the rubric reasons from first principles or the nearest analogue
and **lowers confidence and flags it** -- it never invents a benchmark.
"""
