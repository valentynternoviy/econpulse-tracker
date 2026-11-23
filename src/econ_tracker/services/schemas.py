"""Pydantic v2 request/response DTOs validated strictly at system boundaries."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from econ_tracker.domain.enums import (
    AnomalyStatus,
    HistoryStep,
    TradeSide,
    UserRole,
    WatchDirection,
)


class ProblemDetail(BaseModel):
    """RFC 9457 Problem Details error response."""

    type: str = Field(examples=["urn:econ-tracker:error:not-found"])
    title: str = Field(examples=["Resource not found"])
    status: int = Field(examples=[404])
    detail: str = Field(examples=["Trade #42 was not found"])
    instance: str | None = Field(default=None, examples=["/api/v1/trades/42"])
    request_id: str | None = Field(default=None, examples=["a1b2c3d4e5f6"])

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=6, max_length=128)

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: UserRole
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class GameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    is_active: bool
    items_count: int = 0
    total_offers: int = 0
    total_market_value_usd: Decimal = Decimal("0.00")

class GameCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_-]+$")
    is_active: bool = True

class GameUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    is_active: bool | None = None

class MarketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    game_id: int
    game_code: str = ""
    name: str
    code: str
    base_url: str
    currency: str
    fee_pct: Decimal
    schedule_minutes: int
    is_active: bool
    last_collected_at: datetime | None = None

class MarketCreateRequest(BaseModel):
    game_id: int = Field(gt=0)
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=48, pattern=r"^[a-z0-9_-]+$")
    base_url: str = Field(min_length=8, max_length=255)
    currency: str = Field(min_length=3, max_length=8)
    fee_pct: Decimal = Field(default=Decimal("0.00"), ge=0, le=50)
    schedule_minutes: int = Field(default=15, ge=15, le=1440)
    is_active: bool = True

class MarketUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    fee_pct: Decimal | None = Field(default=None, ge=0, le=50)
    schedule_minutes: int | None = Field(default=None, ge=15, le=1440)
    is_active: bool | None = None

class SubcategoryFacet(BaseModel):
    code: str
    label: str
    items_count: int
    total_volume: int
    shortname: str | None = None
    icon_url: str | None = None

class CategoryFacet(BaseModel):
    code: str
    label: str
    items_count: int
    total_volume: int
    subcategories: list[SubcategoryFacet]

class MarketQuoteDTO(BaseModel):
    market_id: int
    market_code: str
    market_name: str
    original_price: Decimal
    original_currency: str
    normalized_price: Decimal
    exchange_rate: Decimal
    volume: int
    collected_at: datetime
    last_checked_at: datetime

class RelatedItemDTO(BaseModel):
    id: int
    name: str
    name_en: str | None = None
    subcategory: str
    icon_url: str | None = None
    latest_min_price: Decimal | None = None

class ItemSummaryResponse(BaseModel):
    id: int
    game_id: int
    game_code: str
    name: str
    name_en: str | None = None
    normalized_name: str
    item_type: str
    subcategory: str
    base_item_shortname: str | None = None
    set_group: str | None = None
    rarity: str
    external_id: str
    is_available: bool
    icon_url: str | None = None
    description: str | None = None
    released_at: datetime | None = None
    ma7_price: Decimal | None = None
    latest_min_price: Decimal | None = None
    latest_max_price: Decimal | None = None
    latest_total_volume: int = 0
    spread_pct: Decimal | None = None
    price_change_24h_pct: Decimal | None = None
    price_change_7d_pct: Decimal | None = None

class PaginatedItemsResponse(BaseModel):
    items: list[ItemSummaryResponse]
    total: int
    page: int
    page_size: int
    pages: int

class ItemDetailResponse(ItemSummaryResponse):
    markets: list[MarketQuoteDTO]
    cheapest_price: Decimal | None = None
    most_expensive_price: Decimal | None = None
    spread_abs: Decimal | None = None
    related_parts: list[RelatedItemDTO] = Field(default_factory=list)

class PriceHistoryPoint(BaseModel):
    bucket: datetime
    min_price: Decimal
    max_price: Decimal
    avg_price: Decimal
    median_price: Decimal
    avg_volume: int
    snapshots_count: int

class PriceHistoryResponse(BaseModel):
    item_id: int
    item_name: str
    step: HistoryStep
    points: list[PriceHistoryPoint]

class WatchCreateRequest(BaseModel):
    item_id: int = Field(gt=0)
    market_id: int = Field(gt=0)
    direction: WatchDirection
    threshold: Decimal = Field(gt=0)
    cooldown_minutes: int = Field(default=60, ge=0, le=10080)

class WatchUpdateRequest(BaseModel):
    threshold: Decimal | None = Field(default=None, gt=0)
    direction: WatchDirection | None = None
    cooldown_minutes: int | None = Field(default=None, ge=0, le=10080)

class WatchItemResponse(BaseModel):
    id: int
    item_id: int
    item_name: str
    game_code: str
    market_id: int
    market_name: str
    direction: WatchDirection
    threshold: Decimal
    cooldown_minutes: int
    last_alert_at: datetime | None
    created_at: datetime

class AlertResponse(BaseModel):
    id: int
    watch_item_id: int
    item_id: int = 0
    game_code: str = ""
    snapshot_id: int
    triggered_price: Decimal
    message: str
    is_read: bool
    created_at: datetime

class FxRatesResponse(BaseModel):
    usd_to_uah: Decimal
    eur_to_usd: Decimal
    plt_to_usd: Decimal
    source: str

class TradeCreateRequest(BaseModel):
    item_id: int = Field(gt=0)
    market_id: int = Field(gt=0)
    side: TradeSide
    qty: int = Field(gt=0, le=1_000_000)
    price: Decimal = Field(gt=0)
    traded_at: datetime
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)

class TradeResponse(BaseModel):
    id: int
    item_id: int
    item_name: str
    market_id: int
    market_name: str
    side: TradeSide
    quantity: int
    price: Decimal
    traded_at: datetime
    idempotency_key: str
    created_at: datetime

class PositionResponse(BaseModel):
    id: int
    item_id: int
    item_name: str
    game_code: str
    quantity: int
    avg_cost: Decimal
    invested: Decimal
    current_price: Decimal
    current_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    updated_at: datetime

class PortfolioSummaryResponse(BaseModel):
    invested: Decimal
    current_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    positions: list[PositionResponse]
    most_profitable: PositionResponse | None = None
    least_profitable: PositionResponse | None = None

class AnomalyResponse(BaseModel):
    id: int
    item_id: int
    item_name: str
    game_code: str
    market_id: int
    market_name: str
    status: AnomalyStatus
    ma7_price: Decimal
    trigger_price: Decimal
    deviation_pct: Decimal
    max_deviation_pct: Decimal
    opened_at: datetime
    closed_at: datetime | None
    duration_minutes: int
    comment: str | None

class AnomalyCloseRequest(BaseModel):
    comment: str = Field(min_length=3, max_length=1000)

class CollectRunRequest(BaseModel):
    market_id: int | None = Field(default=None, gt=0)

class CollectionRunResponse(BaseModel):
    id: int
    market_id: int
    market_code: str
    market_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    accepted_count: int
    rejected_count: int
    new_snapshots_count: int
    error_message: str | None

class MarketCollectionStatusResponse(BaseModel):
    market_id: int
    market_code: str
    market_name: str
    game_code: str
    currency: str
    schedule_minutes: int
    is_active: bool
    last_run_at: datetime | None
    last_status: str | None
    accepted_count: int
    rejected_count: int
    new_snapshots_count: int
    last_error: str | None

class MoverItemDTO(BaseModel):
    item_id: int
    name: str
    game_code: str
    item_type: str
    rarity: str
    current_price: Decimal
    change_pct: Decimal
    volume: int

class SpreadItemDTO(BaseModel):
    item_id: int
    name: str
    game_code: str
    min_price: Decimal
    max_price: Decimal
    spread_abs: Decimal
    spread_pct: Decimal
    cheapest_market: str
    priciest_market: str

class RarityStatDTO(BaseModel):
    rarity: str
    items_count: int
    avg_price: Decimal
    total_volume: int

class GameIndexDTO(BaseModel):
    game_code: str
    game_name: str
    liquid_items_count: int
    avg_change_24h_pct: Decimal
    avg_change_7d_pct: Decimal
    total_offers: int
    total_market_value_usd: Decimal

class AnalyticsOverviewResponse(BaseModel):
    total_items: int
    total_snapshots: int
    total_offers: int
    total_market_value_usd: Decimal
    game_indices: list[GameIndexDTO]
    top_gainers_24h: list[MoverItemDTO]
    top_losers_24h: list[MoverItemDTO]
    top_gainers_7d: list[MoverItemDTO]
    top_losers_7d: list[MoverItemDTO]
    rarity_stats: list[RarityStatDTO]

ItemSortOption = Literal[
    "newest",
    "price_asc",
    "price_desc",
    "volume_desc",
    "spread_desc",
    "change_desc",
    "name_asc",
]
