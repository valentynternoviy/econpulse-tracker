"""SQLAlchemy 2.0 ORM models representing all entities from the specification."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from econ_tracker.storage.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class GameORM(Base):
    """Tracked game (e.g., Warframe, Rust)."""

    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    markets: Mapped[list[MarketORM]] = relationship(back_populates="game")
    items: Mapped[list[ItemORM]] = relationship(back_populates="game")


class MarketORM(Base):
    """Virtual items marketplace (e.g., Warframe.market PC/PS, Skinport EUR, Rust.tm USD)."""

    __tablename__ = "markets"
    __table_args__ = (
        CheckConstraint("schedule_minutes >= 15", name="ck_markets_schedule_min_15"),
        CheckConstraint("fee_pct >= 0", name="ck_markets_fee_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(48), nullable=False, unique=True, index=True)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    fee_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    schedule_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_collected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    game: Mapped[GameORM] = relationship(back_populates="markets")
    snapshots: Mapped[list[PriceSnapshotORM]] = relationship(back_populates="market")
    collection_runs: Mapped[list[CollectionRunORM]] = relationship(back_populates="market")


class ItemORM(Base):
    """Virtual item / skin tracked across one or more markets."""

    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("game_id", "normalized_name", name="uq_items_game_normalized_name"),
        Index("ix_items_game_type_sub", "game_id", "item_type", "subcategory"),
        Index("ix_items_game_rarity", "game_id", "rarity"),
        Index("ix_items_latest_min_price", "latest_min_price"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(64), nullable=False, default="other")
    subcategory: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    base_item_shortname: Mapped[str | None] = mapped_column(String(80), nullable=True)
    set_group: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    rarity: Mapped[str] = mapped_column(String(32), nullable=False, default="common")
    external_id: Mapped[str] = mapped_column(String(160), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    icon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Precomputed market metrics updated during collection (avoids recomputing MA-7 per page view)
    ma7_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    latest_min_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    latest_max_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    latest_total_volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spread_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    price_change_24h_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    price_change_7d_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    game: Mapped[GameORM] = relationship(back_populates="items")
    snapshots: Mapped[list[PriceSnapshotORM]] = relationship(back_populates="item")


class PriceSnapshotORM(Base):
    """Historical price & offer volume snapshot (M:N link between Item and Market)."""

    __tablename__ = "price_snapshots"
    __table_args__ = (
        CheckConstraint("original_price > 0", name="ck_snapshots_orig_price_pos"),
        CheckConstraint("normalized_price > 0", name="ck_snapshots_norm_price_pos"),
        CheckConstraint("volume >= 0", name="ck_snapshots_volume_non_neg"),
        Index("ix_price_snapshots_item_collected", "item_id", "collected_at"),
        Index("ix_price_snapshots_item_market_collected", "item_id", "market_id", "collected_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    market_id: Mapped[int] = mapped_column(
        ForeignKey("markets.id", ondelete="CASCADE"), nullable=False
    )
    original_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    original_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    normalized_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    last_checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    item: Mapped[ItemORM] = relationship(back_populates="snapshots")
    market: Mapped[MarketORM] = relationship(back_populates="snapshots")


class UserORM(Base):
    """Registered user with role-based permissions."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(24), nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class WatchItemORM(Base):
    """User watch rule on an item/market pair (M:N link between User and Item)."""

    __tablename__ = "watch_items"
    __table_args__ = (
        UniqueConstraint("user_id", "item_id", "market_id", name="uq_watch_user_item_market"),
        CheckConstraint("threshold > 0", name="ck_watch_threshold_pos"),
        CheckConstraint("cooldown_minutes >= 0", name="ck_watch_cooldown_non_neg"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    market_id: Mapped[int] = mapped_column(
        ForeignKey("markets.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    threshold: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    last_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    item: Mapped[ItemORM] = relationship()
    market: Mapped[MarketORM] = relationship()


class AlertORM(Base):
    """Triggered watch alert (idempotent per watch_item + price_snapshot)."""

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("watch_item_id", "snapshot_id", name="uq_alert_watch_snapshot"),
        Index("ix_alerts_user_read_created", "user_id", "is_read", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watch_item_id: Mapped[int] = mapped_column(
        ForeignKey("watch_items.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("price_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    triggered_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    message: Mapped[str] = mapped_column(String(300), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class TradeORM(Base):
    """User portfolio buy/sell trade with idempotency key."""

    __tablename__ = "trades"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_trade_user_idempotency"),
        CheckConstraint("quantity > 0", name="ck_trades_qty_pos"),
        CheckConstraint("price > 0", name="ck_trades_price_pos"),
        Index("ix_trades_user_item_traded_at", "user_id", "item_id", "traded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    market_id: Mapped[int] = mapped_column(
        ForeignKey("markets.id", ondelete="CASCADE"), nullable=False
    )
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    traded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    item: Mapped[ItemORM] = relationship()
    market: Mapped[MarketORM] = relationship()


class PositionORM(Base):
    """Aggregated portfolio position per user & item (retained when quantity reaches 0)."""

    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_position_user_item"),
        CheckConstraint("quantity >= 0", name="ck_positions_qty_non_neg"),
        CheckConstraint("avg_cost >= 0", name="ck_positions_avg_cost_non_neg"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0.0000")
    )
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0.0000")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    item: Mapped[ItemORM] = relationship()


class AnomalyEventORM(Base):
    """Price anomaly event triggered by deviation from 7-day moving average."""

    __tablename__ = "anomaly_events"
    __table_args__ = (Index("ix_anomalies_status_opened", "status", "opened_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    market_id: Mapped[int] = mapped_column(
        ForeignKey("markets.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    ma7_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    trigger_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    deviation_pct: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    max_deviation_pct: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    item: Mapped[ItemORM] = relationship()
    market: Mapped[MarketORM] = relationship()


class CollectionRunORM(Base):
    """Audit log of scheduled or manual collection executions per market."""

    __tablename__ = "collection_runs"
    __table_args__ = (Index("ix_collection_runs_market_started", "market_id", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(
        ForeignKey("markets.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_snapshots_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    market: Mapped[MarketORM] = relationship(back_populates="collection_runs")
