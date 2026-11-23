"""Reproducible performance benchmarks for Chapter 4 of the explanatory note.

Measures:
1. Query execution plan & latency BEFORE vs AFTER composite index (item_id, collected_at).
2. Peak memory consumption (tracemalloc) of LAZY generator pipeline vs EAGER list pipeline.
3. Latency of key portfolio operation (recalculate_position) and precomputed MA-7 vs on-the-fly.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
import tracemalloc
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from econ_tracker.domain.enums import TradeSide
from econ_tracker.domain.logic import recalculate_position, validate_raw_quote
from econ_tracker.domain.models import RawMarketQuote, TradeRecord
from econ_tracker.sources.pipeline import PipelineStats, iter_validated_quotes
from econ_tracker.storage.database import Base, create_engine_and_sessionmaker
from econ_tracker.storage.seed import seed_database


def bench_lazy_vs_eager_memory(n_records: int = 50_000) -> dict[str, object]:
    """Compare peak RAM between eager list materialization and lazy generator pipeline."""
    now = datetime.now(UTC)
    rate = Decimal("1.080000")

    def raw_stream(n: int):  # type: ignore[no-untyped-def]
        for i in range(n):
            price = Decimal("-1") if i % 50 == 0 else Decimal(f"{(i % 200) + 1}.25")
            yield RawMarketQuote(
                external_id=f"ext_{i}",
                name=f"Blackout Hoodie #{i}",
                original_price=price,
                original_currency="EUR",
                volume=i % 100,
                collected_at=now,
                item_type="clothing",
                subcategory="hoodie",
                rarity="rare",
            )

    # 1. Eager approach: materialize raw list + materialize validated list
    tracemalloc.start()
    t0 = time.perf_counter()
    raw_list = list(raw_stream(n_records))
    eager_valid = []
    eager_rejected = 0
    for r in raw_list:
        try:
            eager_valid.append(validate_raw_quote(r, rate_to_usd=rate))
        except Exception:
            eager_rejected += 1
    eager_sum = sum(q.normalized_price for q in eager_valid)
    eager_ms = round((time.perf_counter() - t0) * 1000, 2)
    _, eager_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # 2. Lazy streaming generator pipeline
    tracemalloc.start()
    t1 = time.perf_counter()
    stats = PipelineStats()
    lazy_sum = Decimal("0")
    for q in iter_validated_quotes(raw_stream(n_records), rate_to_usd=rate, stats=stats):
        lazy_sum += q.normalized_price
    lazy_ms = round((time.perf_counter() - t1) * 1000, 2)
    _, lazy_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert eager_sum == lazy_sum
    return {
        "records": n_records,
        "accepted": stats.accepted,
        "rejected": stats.rejected,
        "eager_peak_kb": round(eager_peak / 1024, 1),
        "lazy_peak_kb": round(lazy_peak / 1024, 1),
        "memory_reduction_x": round(eager_peak / max(1, lazy_peak), 1),
        "eager_ms": eager_ms,
        "lazy_ms": lazy_ms,
    }


def bench_key_operation() -> dict[str, object]:
    """Measure latency of chronological portfolio recalculation over 500 trades."""
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    trades = [
        TradeRecord(
            trade_id=i + 1,
            side=TradeSide.BUY if i % 2 == 0 else TradeSide.SELL,
            quantity=2 if i % 2 == 0 else 1,
            price=Decimal("10.00") + Decimal(i % 15),
            traded_at=t0 + timedelta(hours=i),
        )
        for i in range(500)
    ]
    iterations = 200
    start = time.perf_counter()
    for _ in range(iterations):
        recalculate_position(trades)
    avg_ms = ((time.perf_counter() - start) / iterations) * 1000
    return {
        "trades_per_position": 500,
        "iterations": iterations,
        "avg_recalc_ms": round(avg_ms, 3),
    }


async def bench_index_and_ma7() -> dict[str, object]:
    """Compare history query plan/speed BEFORE vs AFTER composite index and MA-7 caching."""
    db_file = "_bench_perf.db"
    if Path(db_file).exists():  # noqa: ASYNC240
        os.remove(db_file)

    eng, sf = create_engine_and_sessionmaker(f"sqlite+aiosqlite:///./{db_file}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with sf() as session:
        seed_res = await seed_database(session, days=30)
    await eng.dispose()

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    query_hist = (
        "SELECT collected_at, normalized_price, volume "
        "FROM price_snapshots "
        "WHERE item_id = 1 AND collected_at >= datetime('now', '-30 days') "
        "ORDER BY collected_at ASC"
    )

    # Drop composite indexes to measure BEFORE state
    cur.execute("DROP INDEX IF EXISTS ix_price_snapshots_item_collected")
    cur.execute("DROP INDEX IF EXISTS ix_price_snapshots_item_market_collected")
    conn.commit()

    plan_before = [row[3] for row in cur.execute(f"EXPLAIN QUERY PLAN {query_hist}").fetchall()]
    t0 = time.perf_counter()
    for _ in range(200):
        cur.execute(query_hist).fetchall()
    before_ms = ((time.perf_counter() - t0) / 200) * 1000

    # Restore composite index (item_id, collected_at) to measure AFTER state
    cur.execute(
        "CREATE INDEX ix_price_snapshots_item_collected "
        "ON price_snapshots (item_id, collected_at)"
    )
    conn.commit()

    plan_after = [row[3] for row in cur.execute(f"EXPLAIN QUERY PLAN {query_hist}").fetchall()]
    t1 = time.perf_counter()
    for _ in range(200):
        cur.execute(query_hist).fetchall()
    after_ms = ((time.perf_counter() - t1) / 200) * 1000

    # Compare catalog page load: on-the-fly MA-7 SQL subquery vs precomputed column on items
    q_onthefly = """
        SELECT i.id, i.name,
               (SELECT AVG(ps.normalized_price) FROM price_snapshots ps
                WHERE ps.item_id = i.id AND ps.collected_at >= datetime('now', '-7 days'))
        FROM items i
        ORDER BY i.latest_total_volume DESC
        LIMIT 24
    """
    q_precomputed = """
        SELECT i.id, i.name, i.ma7_price
        FROM items i
        ORDER BY i.latest_total_volume DESC
        LIMIT 24
    """
    t2 = time.perf_counter()
    for _ in range(100):
        cur.execute(q_onthefly).fetchall()
    onthefly_ms = ((time.perf_counter() - t2) / 100) * 1000

    t3 = time.perf_counter()
    for _ in range(100):
        cur.execute(q_precomputed).fetchall()
    precomputed_ms = ((time.perf_counter() - t3) / 100) * 1000

    conn.close()
    for suffix in ("", "-wal", "-shm"):
        p = db_file + suffix
        if Path(p).exists():  # noqa: ASYNC240
            os.remove(p)

    return {
        "dataset": seed_res,
        "history_plan_before": plan_before,
        "history_plan_after": plan_after,
        "history_avg_ms_before": round(before_ms, 3),
        "history_avg_ms_after": round(after_ms, 3),
        "index_speedup_x": round(before_ms / max(0.001, after_ms), 1),
        "ma7_onthefly_ms": round(onthefly_ms, 3),
        "ma7_precomputed_ms": round(precomputed_ms, 3),
        "ma7_speedup_x": round(onthefly_ms / max(0.001, precomputed_ms), 1),
    }


async def main() -> None:
    report = {
        "lazy_vs_eager_memory": bench_lazy_vs_eager_memory(50_000),
        "key_operation_recalc": bench_key_operation(),
        "index_and_ma7": await bench_index_and_ma7(),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
