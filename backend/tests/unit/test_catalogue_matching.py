"""Region and gap matching for the product catalogue (T3.2)."""

import pytest
from pydantic import ValidationError

from app.modules.commerce.matching import gap_applies, region_applies
from app.modules.commerce.models import ProductKind
from app.modules.commerce.schemas import ProductCreate


class TestRegionApplies:
    def test_global_matches_any_country(self) -> None:
        assert region_applies(["*"], "NG")
        assert region_applies(["*"], "GB")
        assert region_applies(["*"], None)

    def test_named_region_is_case_insensitive(self) -> None:
        assert region_applies(["ng"], "NG")
        assert region_applies(["NG"], "ng")

    def test_other_country_does_not_match(self) -> None:
        assert not region_applies(["NG"], "GB")

    def test_empty_regions_match_nowhere(self) -> None:
        assert not region_applies([], "NG")
        assert not region_applies([], None)

    def test_unknown_country_only_matches_global(self) -> None:
        assert not region_applies(["NG"], None)
        assert region_applies(["NG", "*"], None)


class TestGapApplies:
    def test_overlap_is_enough(self) -> None:
        assert gap_applies(["unit_economics", "team"], ["team"])

    def test_comparison_is_case_insensitive(self) -> None:
        assert gap_applies(["Unit_Economics"], ["unit_economics"])

    def test_empty_tags_are_browse_only(self) -> None:
        assert not gap_applies([], ["unit_economics"])

    def test_no_overlap(self) -> None:
        assert not gap_applies(["team"], ["traction"])


class TestProductCreateValidation:
    def test_event_requires_when_and_where(self) -> None:
        with pytest.raises(ValidationError):
            ProductCreate(
                kind=ProductKind.EVENT,
                slug="lagos-demo-day",
                title="Lagos demo day",
                regions=["NG"],
            )

    def test_amount_requires_currency(self) -> None:
        with pytest.raises(ValidationError):
            ProductCreate(
                kind=ProductKind.PROGRAM,
                slug="clinic",
                title="Clinic",
                regions=["*"],
                amount_minor=15000,
            )

    def test_regions_must_be_iso_or_star(self) -> None:
        with pytest.raises(ValidationError):
            ProductCreate(
                kind=ProductKind.PROGRAM,
                slug="clinic",
                title="Clinic",
                regions=["Nigeria"],
            )

    def test_slug_is_normalised_shape(self) -> None:
        with pytest.raises(ValidationError):
            ProductCreate(
                kind=ProductKind.PROGRAM,
                slug="Unit Economics",
                title="Clinic",
                regions=["*"],
            )
