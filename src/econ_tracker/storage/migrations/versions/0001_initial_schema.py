"""Initial schema with all entities, constraints, and composite indexes.

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-11-23 18:35:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "games",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_games_code", "games", ["code"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "markets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=48), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("fee_pct", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("schedule_minutes", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("schedule_minutes >= 15", name="ck_markets_schedule_min_15"),
        sa.CheckConstraint("fee_pct >= 0", name="ck_markets_fee_non_negative"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_markets_code", "markets", ["code"], unique=True)

    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("item_type", sa.String(length=64), nullable=False),
        sa.Column("subcategory", sa.String(length=64), nullable=False),
        sa.Column("rarity", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=160), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("icon_url", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ma7_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("latest_min_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("latest_max_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("latest_total_volume", sa.Integer(), nullable=False),
        sa.Column("spread_pct", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("price_change_24h_pct", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("price_change_7d_pct", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "normalized_name", name="uq_items_game_normalized_name"),
    )
    op.create_index("ix_items_name", "items", ["name"])
    op.create_index("ix_items_normalized_name", "items", ["normalized_name"])
    op.create_index("ix_items_game_type_sub", "items", ["game_id", "item_type", "subcategory"])
    op.create_index("ix_items_game_rarity", "items", ["game_id", "rarity"])
    op.create_index("ix_items_latest_min_price", "items", ["latest_min_price"])

    op.create_table(
        "price_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("original_price", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("original_currency", sa.String(length=8), nullable=False),
        sa.Column("normalized_price", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("original_price > 0", name="ck_snapshots_orig_price_pos"),
        sa.CheckConstraint("normalized_price > 0", name="ck_snapshots_norm_price_pos"),
        sa.CheckConstraint("volume >= 0", name="ck_snapshots_volume_non_neg"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_price_snapshots_item_collected",
        "price_snapshots",
        ["item_id", "collected_at"],
    )
    op.create_index(
        "ix_price_snapshots_item_market_collected",
        "price_snapshots",
        ["item_id", "market_id", "collected_at"],
    )

    op.create_table(
        "watch_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("threshold", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False),
        sa.Column("last_alert_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("threshold > 0", name="ck_watch_threshold_pos"),
        sa.CheckConstraint("cooldown_minutes >= 0", name="ck_watch_cooldown_non_neg"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "item_id", "market_id", name="uq_watch_user_item_market"),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("watch_item_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("triggered_price", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("message", sa.String(length=300), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["watch_item_id"], ["watch_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["price_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("watch_item_id", "snapshot_id", name="uq_alert_watch_snapshot"),
    )
    op.create_index("ix_alerts_user_read_created", "alerts", ["user_id", "is_read", "created_at"])

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("traded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_trades_qty_pos"),
        sa.CheckConstraint("price > 0", name="ck_trades_price_pos"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_trade_user_idempotency"),
    )
    op.create_index("ix_trades_user_item_traded_at", "trades", ["user_id", "item_id", "traded_at"])

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("avg_cost", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_positions_qty_non_neg"),
        sa.CheckConstraint("avg_cost >= 0", name="ck_positions_avg_cost_non_neg"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "item_id", name="uq_position_user_item"),
    )

    op.create_table(
        "anomaly_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("ma7_price", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("trigger_price", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("deviation_pct", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("max_deviation_pct", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["closed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_anomalies_status_opened", "anomaly_events", ["status", "opened_at"])

    op.create_table(
        "collection_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("new_snapshots_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collection_runs_market_started",
        "collection_runs",
        ["market_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_table("collection_runs")
    op.drop_table("anomaly_events")
    op.drop_table("positions")
    op.drop_table("trades")
    op.drop_table("alerts")
    op.drop_table("watch_items")
    op.drop_table("price_snapshots")
    op.drop_table("items")
    op.drop_table("markets")
    op.drop_table("users")
    op.drop_table("games")
