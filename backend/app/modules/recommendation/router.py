"""Recommendation HTTP endpoints (T5.1 / T5.2)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import CurrentUserDep, SessionDep
from app.core.errors import error_responses
from app.modules.recommendation import service
from app.modules.recommendation.schemas import RecommendationPage

router = APIRouter(tags=["recommendation"])


@router.get(
    "/startups/{startup_id}/recommendations",
    response_model=RecommendationPage,
    summary="Gap → program recommendations for a startup",
    responses=error_responses(401, 403, 404),
)
async def startup_recommendations(
    startup_id: uuid.UUID,
    actor: CurrentUserDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> RecommendationPage:
    return await service.recommend_for_startup(
        session, actor, startup_id, limit=limit
    )


@router.get(
    "/recommendations",
    response_model=RecommendationPage,
    summary="Browse programmes for a country",
    responses=error_responses(401, 403, 404),
)
async def country_recommendations(
    actor: CurrentUserDep,
    session: SessionDep,
    country: Annotated[str, Query(min_length=2, max_length=2)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> RecommendationPage:
    return await service.recommend_for_country(
        session, actor, country=country, limit=limit
    )
