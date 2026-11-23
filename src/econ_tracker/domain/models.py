"""Pure domain value objects and entities with strict invariant checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from econ_tracker.domain.enums import TradeSide, WatchDirection
from econ_tracker.domain.exceptions import DomainValidationError


@dataclass(frozen=True, slots=True)
class RawMarketQuote:
    """Unvalidated record yielded lazily by an external market adapter."""

    external_id: str
    name: str
    original_price: Decimal | None
    original_currency: str
    volume: int | None
    collected_at: datetime
    item_type: str = "other"
    subcategory: str = "general"
    rarity: str = "common"
    icon_url: str | None = None
    description: str | None = None
    released_at: datetime | None = None
    extra_tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidatedQuote:
    """Normalized and validated market price quote ready for persistence."""

    external_id: str
    name: str
    normalized_name: str
    original_price: Decimal
    original_currency: str
    normalized_price: Decimal
    exchange_rate: Decimal
    volume: int
    collected_at: datetime
    item_type: str
    subcategory: str
    rarity: str
    icon_url: str | None = None
    description: str | None = None
    released_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise DomainValidationError("Item name must not be empty")
        if not self.normalized_name.strip():
            raise DomainValidationError("Normalized item name must not be empty")
        if self.original_price <= Decimal("0"):
            raise DomainValidationError("Original price must be strictly positive")
        if self.normalized_price <= Decimal("0"):
            raise DomainValidationError("Normalized price must be strictly positive")
        if self.exchange_rate <= Decimal("0"):
            raise DomainValidationError("Exchange rate must be strictly positive")
        if self.volume < 0:
            raise DomainValidationError("Volume must be non-negative")


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """Single buy/sell trade used for deterministic chronological position recalculation."""

    trade_id: int
    side: TradeSide
    quantity: int
    price: Decimal
    traded_at: datetime

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise DomainValidationError("Trade quantity must be strictly positive")
        if self.price <= Decimal("0"):
            raise DomainValidationError("Trade price must be strictly positive")


@dataclass(frozen=True, slots=True)
class PositionState:
    """Calculated state of a user's portfolio position for a single item."""

    quantity: int
    avg_cost: Decimal
    realized_pnl: Decimal

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise DomainValidationError("Position quantity cannot be negative")
        if self.avg_cost < Decimal("0"):
            raise DomainValidationError("Position average cost cannot be negative")

    @property
    def invested_amount(self) -> Decimal:
        """Total capital currently locked in open quantity."""
        return (self.avg_cost * Decimal(self.quantity)).quantize(Decimal("0.0001"))


@dataclass(frozen=True, slots=True)
class WatchRule:
    """User watch threshold configuration."""

    direction: WatchDirection
    threshold: Decimal
    cooldown_minutes: int = 60

    def __post_init__(self) -> None:
        if self.threshold <= Decimal("0"):
            raise DomainValidationError("Watch threshold must be strictly positive")
        if self.cooldown_minutes < 0:
            raise DomainValidationError("Cooldown minutes must be non-negative")


@dataclass(frozen=True, slots=True)
class AnomalyCheckResult:
    """Decision returned by the pure anomaly detection rule."""

    action: Literal["open", "update", "close", "none"]
    deviation_pct: Decimal
    max_deviation_pct: Decimal
