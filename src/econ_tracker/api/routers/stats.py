"""Analytics and market spread statistics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from econ_tracker.api.deps import AppContainer, get_container, get_session
from econ_tracker.api.errors import COMMON_ERROR_RESPONSES
from econ_tracker.services.schemas import (
    AnalyticsOverviewResponse,
    MarketResponse,
    SpreadItemDTO,
)

router = APIRouter(prefix="/api/v1", tags=["Analytics & Markets"], responses=COMMON_ERROR_RESPONSES)


@router.get("/stats/overview", response_model=AnalyticsOverviewResponse)
async def stats_overview(
    game: str | None = Query(default=None, max_length=32),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> AnalyticsOverviewResponse:
    return await container.analytics_service.get_overview(session, game=game)


@router.get("/stats/spread", response_model=list[SpreadItemDTO])
async def stats_spread(
    game: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=20, ge=1, le=100),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> list[SpreadItemDTO]:
    return await container.analytics_service.get_spreads(session, game=game, limit=limit)


@router.get("/markets", response_model=list[MarketResponse])
async def list_markets(
    game: str | None = Query(default=None, max_length=32),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> list[MarketResponse]:
    return await container.admin_service.list_markets(session, game=game)
