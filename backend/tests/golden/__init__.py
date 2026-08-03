"""T2.9 golden set: hand-scored companies and the loader that reads them.

Split from `tests/unit` because the fixtures are a reviewable artefact in their
own right -- somebody has to sit down and decide what each company's audit
*should* say, and that decision needs to live somewhere a non-author can find
and correct it.

Every expectation now carries `reviewed_by`, and **that field is the point of
this package**. Two companies are `deterministic`: their verdict falls out of
the integrity floor or the coverage ratio, so no judgement of anybody's is in
them. The other six are `assistant-draft` -- scored by Claude against the
published rubric, which is the same model family the audit engine runs on. An
eval report that blends the two into one percentage is reporting a model
agreeing with itself and calling it accuracy. `qualified_ids` exists so that
cannot happen by omission.
"""

from tests.golden.loader import (
    ExpectedVerdict,
    GoldenCompany,
    ReviewedBy,
    load_companies,
    qualified_ids,
    reviewed_companies,
)

__all__ = [
    "ExpectedVerdict",
    "GoldenCompany",
    "ReviewedBy",
    "load_companies",
    "qualified_ids",
    "reviewed_companies",
]
