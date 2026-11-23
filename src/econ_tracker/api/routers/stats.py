"""Analytics and market spread statistics endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from econ_tracker.api.deps import AppContainer, get_container, get_session
from econ_tracker.api.errors import COMMON_ERROR_RESPONSES
from econ_tracker.services.schemas import (
    AnalyticsOverviewResponse,
    FxRatesResponse,
    MarketResponse,
    SpreadItemDTO,
)

router = APIRouter(prefix="/api/v1", tags=["Analytics & Markets"], responses=COMMON_ERROR_RESPONSES)

_FX_CACHE_TTL = timedelta(hours=1)
_fx_cache: tuple[datetime, FxRatesResponse] | None = None


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


@router.get("/fx-rates", response_model=FxRatesResponse)
async def get_fx_rates(
    container: AppContainer = Depends(get_container),
) -> FxRatesResponse:
    """Return USD/UAH, EUR/USD, and PLT/USD rates (cached 1h from NBU with safe fallback)."""
    global _fx_cache
    now = datetime.now(UTC)
    if _fx_cache is not None and now - _fx_cache[0] < _FX_CACHE_TTL:
        return _fx_cache[1]

    plt_rate = container.settings.platinum_usd_rate
    usd_to_uah = Decimal("41.50")
    eur_to_usd = Decimal("1.0800")
    source = "fallback"

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json"
            )
            resp.raise_for_status()
            rows = resp.json()
            uah_usd: Decimal | None = None
            uah_eur: Decimal | None = None
            for row in rows:
                cc = str(row.get("cc", "")).upper()
                if cc == "USD":
                    uah_usd = Decimal(str(row["rate"]))
                elif cc == "EUR":
                    uah_eur = Decimal(str(row["rate"]))
            if uah_usd and uah_usd > Decimal("0"):
                usd_to_uah = uah_usd.quantize(Decimal("0.01"))
                if uah_eur and uah_eur > Decimal("0"):
                    eur_to_usd = (uah_eur / uah_usd).quantize(Decimal("0.0001"))
                source = "nbu"
    except Exception:
        pass

    result = FxRatesResponse(
        usd_to_uah=usd_to_uah,
        eur_to_usd=eur_to_usd,
        plt_to_usd=plt_rate,
        source=source,
    )
    _fx_cache = (now, result)
    return result
