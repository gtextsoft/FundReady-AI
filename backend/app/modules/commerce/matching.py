"""Pure catalogue matching (T3.2).

Region relevance and gap-tag overlap live here so the rules can be reviewed
and unit-tested without a database. SQL filters apply the same predicates;
this module is the source of truth for what those predicates mean.
"""

from collections.abc import Sequence

GLOBAL_REGION = "*"


def normalise_region(value: str) -> str:
    """ISO alpha-2, uppercased. `*` stays `*`."""
    stripped = value.strip()
    if stripped == GLOBAL_REGION:
        return GLOBAL_REGION
    return stripped.upper()


def region_applies(regions: Sequence[str], country: str | None) -> bool:
    """Whether a catalogue item is listed for this country.

    `*` is the global wildcard (same convention as benchmarks). A product
    with no regions is listed nowhere — an empty list is not "everywhere",
    because that would make a forgotten `regions` field silently worldwide.
    `country is None` only matches global items: a startup that has not
    named a country still sees programmes SACI marked as everywhere.
    """
    normalised = {normalise_region(item) for item in regions if item.strip()}
    if GLOBAL_REGION in normalised:
        return True
    if country is None or not country.strip():
        return False
    return normalise_region(country) in normalised


def gap_applies(gap_tags: Sequence[str], gaps: Sequence[str]) -> bool:
    """Whether a catalogue item is relevant to any of these gaps.

    Tags are compared case-insensitively. An item with no tags is
    browse-only — it appears in `GET /v1/products` but is not a
    recommendation, because an empty tag list is not "matches everything".
    """
    tagged = {tag.strip().lower() for tag in gap_tags if tag.strip()}
    if not tagged:
        return False
    asked = {gap.strip().lower() for gap in gaps if gap.strip()}
    return bool(tagged & asked)
