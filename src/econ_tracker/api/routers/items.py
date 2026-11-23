"""Catalog, category facets, item detail card, and aggregated price history (JSON & CSV)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from econ_tracker.api.deps import AppContainer, get_container, get_session
from econ_tracker.api.errors import COMMON_ERROR_RESPONSES
from econ_tracker.domain.enums import HistoryStep
from econ_tracker.services.schemas import (
    CategoryFacet,
    GameResponse,
    ItemDetailResponse,
    ItemSortOption,
    PaginatedItemsResponse,
    PriceHistoryResponse,
)

router = APIRouter(prefix="/api/v1", tags=["Catalog"], responses=COMMON_ERROR_RESPONSES)


@router.get("/games", response_model=list[GameResponse])
async def list_games(
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> list[GameResponse]:
    return await container.analytics_service.list_games_with_totals(session)


@router.get("/categories", response_model=list[CategoryFacet])
async def list_categories(
    game: str | None = Query(default=None, description="Game code (warframe, rust)"),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> list[CategoryFacet]:
    return await container.catalog_service.get_category_facets(session, game=game)


@router.get("/items", response_model=PaginatedItemsResponse)
async def list_items(
    q: str | None = Query(default=None, max_length=120),
    game: str | None = Query(default=None, max_length=32),
    item_type: str | None = Query(default=None, max_length=64),
    subcategory: str | None = Query(default=None, max_length=64),
    rarity: str | None = Query(default=None, max_length=32),
    market: str | None = Query(default=None, max_length=48),
    price_min: Decimal | None = Query(default=None, ge=0),
    price_max: Decimal | None = Query(default=None, ge=0),
    available_only: bool = Query(default=False),
    sort: ItemSortOption = Query(default="volume_desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> PaginatedItemsResponse:
    return await container.catalog_service.list_items(
        session,
        q=q,
        game=game,
        item_type=item_type,
        subcategory=subcategory,
        rarity=rarity,
        market=market,
        price_min=price_min,
        price_max=price_max,
        available_only=available_only,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/items/{item_id}", response_model=ItemDetailResponse)
async def get_item_detail(
    item_id: int,
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> ItemDetailResponse:
    return await container.catalog_service.get_item_detail(session, item_id=item_id)


@router.get(
    "/items/{item_id}/prices",
    response_model=PriceHistoryResponse,
    summary="Aggregated price & volume history (JSON or CSV export)",
)
async def get_item_prices(
    item_id: int,
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    step: HistoryStep = Query(default=HistoryStep.DAY),
    market_id: int | None = Query(default=None, gt=0),
    export_format: Literal["json", "csv"] = Query(default="json", alias="format"),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> PriceHistoryResponse | Response:
    history = await container.catalog_service.get_price_history(
        session,
        item_id=item_id,
        date_from=date_from,
        date_to=date_to,
        step=step,
        market_id=market_id,
    )
    if export_format == "csv":
        csv_body = container.catalog_service.render_history_csv(history)
        filename = f"item_{item_id}_history_{step.value}.csv"
        return Response(
            content=csv_body,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return history
