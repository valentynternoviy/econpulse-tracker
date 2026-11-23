"""Unit tests for pure domain models, portfolio math, alerts, anomalies, and lazy pipeline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from econ_tracker.domain import (
    DomainValidationError,
    InsufficientPositionError,
    RawMarketQuote,
    TradeRecord,
    TradeSide,
    WatchDirection,
    WatchRule,
    classify_rust_item,
    classify_warframe_item,
    convert_currency,
    evaluate_anomaly,
    normalize_item_name,
    recalculate_position,
    should_create_snapshot,
    should_trigger_watch,
    validate_raw_quote,
)
from econ_tracker.sources.pipeline import PipelineStats, iter_validated_quotes


@pytest.mark.unit
def test_normalize_and_currency_conversion() -> None:
    assert normalize_item_name("  AK-47 | Alien Red! ") == "ak_47_alien_red"
    assert convert_currency(Decimal("10.00"), Decimal("1.085")) == Decimal("10.8500")
    with pytest.raises(DomainValidationError):
        convert_currency(Decimal("0"), Decimal("1.08"))


@pytest.mark.unit
def test_classifications_for_rust_and_warframe() -> None:
    assert classify_rust_item("Blackout Hoodie") == ("clothing", "hoodie", "rare")
    assert classify_rust_item("Alien Red AK47") == ("weapons", "ak47", "legendary")
    assert classify_rust_item("Dragon Furnace") == ("deployables", "furnace", "rare")
    assert classify_rust_item("Tactical Hatchet") == ("tools", "hatchet", "uncommon")
    assert classify_rust_item("Lumberjack Hatchet") == ("tools", "hatchet", "common")

    assert classify_warframe_item(["prime", "warframe", "set"], "Gauss Prime Set") == (
        "warframes",
        "prime_set",
        "prime",
    )
    assert classify_warframe_item(["arcane_enhancement"], "Arcane Energize") == (
        "arcanes",
        "arcane",
        "rare",
    )
    assert classify_warframe_item(["mod", "aura"], "Brief Respite") == ("mods", "aura", "common")
    # Augment mods also carry the "warframe" tag — must still classify under mods, never warframes
    assert classify_warframe_item(
        ["mod", "zephyr", "warframe", "augment", "rare"], "Target Fixation"
    ) == ("mods", "augment", "rare")
    assert classify_warframe_item(["mod", "rifle", "primary", "rare"], "Split Chamber") == (
        "mods",
        "mod",
        "rare",
    )


@pytest.mark.unit
def test_recalculate_position_weighted_avg_and_realized_pnl() -> None:
    t0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    trades = [
        TradeRecord(1, TradeSide.BUY, 2, Decimal("100.00"), t0),
        TradeRecord(2, TradeSide.BUY, 2, Decimal("140.00"), t0 + timedelta(days=1)),
        # Weighted avg is (200 + 280) / 4 = 120.00
        TradeRecord(3, TradeSide.SELL, 3, Decimal("150.00"), t0 + timedelta(days=2)),
        # Realized PnL = (150 - 120) * 3 = 90.00; qty remaining = 1 @ 120.00
    ]
    state = recalculate_position(trades)
    assert state.quantity == 1
    assert state.avg_cost == Decimal("120.0000")
    assert state.realized_pnl == Decimal("90.0000")
    assert state.invested_amount == Decimal("120.0000")


@pytest.mark.unit
def test_recalculate_position_backdated_trade_recomputes_chronologically() -> None:
    t0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    # Trade #3 was inserted later with an EARLIER timestamp (backdated)
    trades = [
        TradeRecord(1, TradeSide.BUY, 1, Decimal("100.00"), t0 + timedelta(days=2)),
        TradeRecord(2, TradeSide.SELL, 1, Decimal("120.00"), t0 + timedelta(days=3)),
        TradeRecord(3, TradeSide.BUY, 1, Decimal("60.00"), t0),
    ]
    state = recalculate_position(trades)
    # Chronologically: Buy 1@60 -> Buy 1@100 (avg=80, qty=2) -> Sell 1@120 (pnl=+40, qty=1)
    assert state.quantity == 1
    assert state.avg_cost == Decimal("80.0000")
    assert state.realized_pnl == Decimal("40.0000")


@pytest.mark.unit
def test_recalculate_position_rejects_oversell_and_preserves_zero_qty_pnl() -> None:
    t0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    with pytest.raises(InsufficientPositionError):
        recalculate_position(
            [
                TradeRecord(1, TradeSide.BUY, 2, Decimal("10.00"), t0),
                TradeRecord(2, TradeSide.SELL, 3, Decimal("15.00"), t0 + timedelta(hours=1)),
            ]
        )

    closed = recalculate_position(
        [
            TradeRecord(1, TradeSide.BUY, 2, Decimal("10.00"), t0),
            TradeRecord(2, TradeSide.SELL, 2, Decimal("15.00"), t0 + timedelta(hours=1)),
        ]
    )
    assert closed.quantity == 0
    assert closed.avg_cost == Decimal("0.0000")
    assert closed.realized_pnl == Decimal("10.0000")


@pytest.mark.unit
def test_watch_trigger_crossing_and_quiet_cooldown() -> None:
    now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    # Crossing from above (12 -> 9) below threshold 10 triggers
    assert should_trigger_watch(
        direction=WatchDirection.BELOW,
        threshold=Decimal("10"),
        current_price=Decimal("9"),
        previous_price=Decimal("12"),
        last_alert_at=None,
        cooldown_minutes=60,
        now=now,
    )
    # Staying below threshold (9 -> 8) must NOT re-trigger
    assert not should_trigger_watch(
        direction=WatchDirection.BELOW,
        threshold=Decimal("10"),
        current_price=Decimal("8"),
        previous_price=Decimal("9"),
        last_alert_at=None,
        cooldown_minutes=60,
        now=now,
    )
    # Crossing during quiet pause must NOT trigger
    assert not should_trigger_watch(
        direction=WatchDirection.BELOW,
        threshold=Decimal("10"),
        current_price=Decimal("9"),
        previous_price=Decimal("12"),
        last_alert_at=now - timedelta(minutes=20),
        cooldown_minutes=60,
        now=now,
    )
    with pytest.raises(DomainValidationError):
        WatchRule(direction=WatchDirection.ABOVE, threshold=Decimal("0"))


@pytest.mark.unit
def test_anomaly_lifecycle_open_update_and_autoclose() -> None:
    open_res = evaluate_anomaly(
        current_price=Decimal("130"),
        ma7_price=Decimal("100"),
        threshold_pct=Decimal("20"),
        has_open_event=False,
    )
    assert open_res.action == "open"
    assert open_res.deviation_pct == Decimal("30.00")

    upd_res = evaluate_anomaly(
        current_price=Decimal("145"),
        ma7_price=Decimal("100"),
        threshold_pct=Decimal("20"),
        has_open_event=True,
        existing_max_deviation=Decimal("30.00"),
    )
    assert upd_res.action == "update"
    assert upd_res.max_deviation_pct == Decimal("45.00")

    close_res = evaluate_anomaly(
        current_price=Decimal("105"),
        ma7_price=Decimal("100"),
        threshold_pct=Decimal("20"),
        has_open_event=True,
        existing_max_deviation=Decimal("45.00"),
    )
    assert close_res.action == "close"


@pytest.mark.unit
def test_lazy_pipeline_skips_dirty_records_and_deduplication_rule() -> None:
    now = datetime.now(UTC)
    raw = [
        RawMarketQuote("id1", "Valid Skin", Decimal("10"), "EUR", 5, now),
        RawMarketQuote("id2", "Zero Price", Decimal("0"), "EUR", 5, now),
        RawMarketQuote("id3", "Negative Vol", Decimal("10"), "EUR", -1, now),
        RawMarketQuote("id4", "   ", Decimal("10"), "EUR", 2, now),
    ]
    stats = PipelineStats()
    valid = list(iter_validated_quotes(raw, rate_to_usd=Decimal("1.10"), stats=stats))
    assert len(valid) == 1
    assert valid[0].normalized_price == Decimal("11.0000")
    assert stats.accepted == 1
    assert stats.rejected == 3

    assert not should_create_snapshot(Decimal("11.0000"), 5, Decimal("11.0000"), 5)
    assert should_create_snapshot(Decimal("11.0000"), 5, Decimal("11.5000"), 5)
    assert should_create_snapshot(Decimal("11.0000"), 5, Decimal("11.0000"), 6)

    with pytest.raises(DomainValidationError):
        validate_raw_quote(raw[1], rate_to_usd=Decimal("1.0"))
