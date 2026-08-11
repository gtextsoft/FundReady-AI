"""Recommendation response schemas (T5.1 / T5.2)."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RecommendedProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    slug: str
    title: str
    kind: str
    score: int = Field(description="Match strength against the gap tags.")
    matched_tags: list[str] = Field(default_factory=list)


class RecommendationPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RecommendedProduct]
    country: str | None = None
