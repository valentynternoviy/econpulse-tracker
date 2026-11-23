"""Idempotent database seeder loading real Rust skins (SCMM) and Ukrainian Warframe items."""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import bcrypt
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from econ_tracker.domain.enums import AnomalyStatus, CollectionStatus, TradeSide, UserRole
from econ_tracker.domain.logic import (
    classify_warframe_item,
    convert_currency,
    normalize_item_name,
    recalculate_position,
)
from econ_tracker.domain.models import TradeRecord
from econ_tracker.logging_config import get_logger
from econ_tracker.storage.orm_models import (
    AlertORM,
    AnomalyEventORM,
    CollectionRunORM,
    GameORM,
    ItemORM,
    MarketORM,
    PositionORM,
    PriceSnapshotORM,
    TradeORM,
    UserORM,
    WatchItemORM,
)

logger = get_logger(__name__)

_Q4 = Decimal("0.0001")
_Q2 = Decimal("0.01")
_CACHE_PATH = Path(__file__).resolve().parent / "real_catalog_cache.json"


@dataclass(frozen=True, slots=True)
class _SeedItemSpec:
    name: str
    name_en: str | None
    normalized_name: str
    item_type: str
    subcategory: str
    base_item_shortname: str | None
    rarity: str
    external_id: str
    base_usd: float
    base_vol: int
    icon_url: str | None
    description: str | None
    released_at: datetime | None
    history_days: int
    anomaly_spike: float = 0.0


def _parse_iso_dt(raw: str | None, fallback: datetime) -> datetime:
    if not raw:
        return fallback
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    except ValueError:
        return fallback


def _infer_rust_rarity(price_usd: float, has_glow: bool, is_twitch: bool) -> str:
    if price_usd >= 35.0 or has_glow:
        return "legendary"
    if price_usd >= 10.0 or is_twitch:
        return "rare"
    if price_usd >= 3.0:
        return "uncommon"
    return "common"


def _load_real_specs(
    *,
    now: datetime,
    days: int,
    max_items_per_game: int | None,
) -> tuple[list[_SeedItemSpec], list[_SeedItemSpec]]:
    cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    plt_to_usd = 0.04999

    # ---------------- RUST SPECS ----------------
    rust_raw: list[dict[str, Any]] = cache.get("rust", [])
    # Stratified round-robin sampling by base_type when capped (used by fast tests)
    if max_items_per_game is not None and len(rust_raw) > max_items_per_game:
        by_sub: dict[str, list[dict[str, Any]]] = {}
        for r in rust_raw:
            by_sub.setdefault(str(r.get("base_type") or "Misc"), []).append(r)
        sampled_rust: list[dict[str, Any]] = []
        sub_lists = list(by_sub.values())
        idx_c = 0
        while len(sampled_rust) < max_items_per_game and sub_lists:
            lst = sub_lists[idx_c % len(sub_lists)]
            if lst:
                sampled_rust.append(lst.pop(0))
                idx_c += 1
            else:
                sub_lists.pop(idx_c % len(sub_lists))
        rust_raw = sampled_rust

    rust_specs: list[_SeedItemSpec] = []
    seen_rust: set[str] = set()

    # Ensure Blackout Hoodie is always present for deterministic test queries
    def _append_rust(row: dict[str, Any], idx: int) -> None:
        name = str(row["name"]).strip()
        norm = normalize_item_name(name)
        if not norm or norm in seen_rust:
            return
        seen_rust.add(norm)
        price_usd = float(row.get("price_usd") or 2.49)
        vol = int(row.get("volume") or 20)
        base_type = str(row.get("base_type") or "Misc")
        cat = str(row.get("category") or "other")
        sub = normalize_item_name(base_type) or "misc"
        shortname = str(row.get("shortname") or "") or None
        icon_url = str(row.get("icon_large_url") or row.get("icon_url") or "") or None
        rarity = _infer_rust_rarity(
            price_usd,
            bool(row.get("has_glow")),
            bool(row.get("is_twitch_drop")),
        )
        released = _parse_iso_dt(row.get("released_at"), now - timedelta(days=365 + idx * 3))
        spike = 0.34 if idx == 0 else (-0.28 if idx == 2 else 0.0)
        hist_days = days if idx < 180 else min(days, 5)
        rust_specs.append(
            _SeedItemSpec(
                name=name,
                name_en=name,
                normalized_name=norm,
                item_type=cat,
                subcategory=sub,
                base_item_shortname=shortname,
                rarity=rarity,
                external_id=name,
                base_usd=price_usd,
                base_vol=vol,
                icon_url=icon_url,
                description=None,
                released_at=released,
                history_days=hist_days,
                anomaly_spike=spike,
            )
        )

    for idx, row in enumerate(rust_raw):
        _append_rust(row, idx)

    if "blackout_hoodie" not in seen_rust:
        _append_rust(
            {
                "name": "Blackout Hoodie",
                "category": "clothing",
                "base_type": "Hoodie",
                "shortname": "hoodie",
                "icon_url": "https://wiki.rustclash.com/img/skins/180/10105.png",
                "price_usd": 11.40,
                "volume": 88,
                "released_at": "2020-05-14T18:00:00Z",
            },
            len(rust_specs),
        )

    # ---------------- WARFRAME UKRAINIAN SPECS ----------------
    wf_all: list[dict[str, Any]] = cache.get("warframe", [])
    gauss_entry = next((x for x in wf_all if x.get("slug") == "gauss_prime_set"), None)
    wf_raw = wf_all[:max_items_per_game] if max_items_per_game is not None else wf_all

    wf_specs: list[_SeedItemSpec] = []
    seen_wf: set[str] = set()

    def _append_wf(row: dict[str, Any], idx: int) -> None:
        slug = str(row["slug"]).strip()
        name_uk = str(row.get("name_uk") or row.get("name_en") or slug).strip()
        name_en = str(row.get("name_en") or name_uk).strip()
        norm = normalize_item_name(name_en)
        if not norm or norm in seen_wf:
            return
        seen_wf.add(norm)
        tags: list[str] = [str(t) for t in row.get("tags", [])]
        cat, sub, rarity = classify_warframe_item(tags, name_en)

        rng_seed = int(hashlib.sha256(slug.encode()).hexdigest()[:8], 16)
        rng = random.Random(rng_seed)
        if cat == "warframes" and sub == "prime_set":
            plt = rng.randint(45, 145)
        elif cat == "arcanes":
            plt = rng.randint(25, 380)
        elif cat == "mods" and rarity == "legendary":
            plt = rng.randint(65, 120)
        elif cat == "weapons" and "set" in sub:
            plt = rng.randint(24, 150)
        else:
            plt = rng.randint(10, 55)

        if slug == "gauss_prime_set":
            plt = 52
        vol = rng.randint(18, 195)
        desc = str(row.get("description") or "").strip() or (
            f"Ігровий предмет Warframe ({name_en}). Доступний для торгівлі між гравцями за Платину."
        )
        spike = 0.35 if slug == "gauss_prime_set" else (0.28 if idx == 3 else 0.0)
        hist_days = days if idx < 140 else min(days, 5)
        wf_specs.append(
            _SeedItemSpec(
                name=name_uk,
                name_en=name_en,
                normalized_name=norm,
                item_type=cat,
                subcategory=sub,
                base_item_shortname=None,
                rarity=rarity,
                external_id=slug,
                base_usd=round(plt * plt_to_usd, 4),
                base_vol=vol,
                icon_url=str(row.get("icon_url") or "") or None,
                description=desc,
                released_at=now - timedelta(days=140 + (idx * 29) % 1600),
                history_days=hist_days,
                anomaly_spike=spike,
            )
        )

    # Guarantee Gauss Prime Set is always included (even if beyond slice or missing from top 420)
    gauss_entry = next(
        (x for x in wf_all if x.get("slug") == "gauss_prime_set"),
        {
            "slug": "gauss_prime_set",
            "name_uk": "Ґаусс-Прайм (комплект)",
            "name_en": "Gauss Prime Set",
            "tags": ["prime", "warframe", "set"],
            "icon_url": "https://warframe.market/static/assets/items/images/en/gauss_prime_set.df5aa569d863730a4de767fd449c107e.png",
            "description": "Ртуть набуває форми. Ґаусс-прайм не хоче навіть чути про поразку.",
        },
    )
    _append_wf(gauss_entry, 0)

    for idx, row in enumerate(wf_raw, start=1):
        _append_wf(row, idx)

    return wf_specs, rust_specs


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def seed_database(
    session: AsyncSession,
    *,
    if_empty: bool = False,
    days: int = 30,
    max_items_per_game: int | None = None,
    eur_to_usd: Decimal = Decimal("1.080000"),
    plt_to_usd: Decimal = Decimal("0.049990"),
) -> dict[str, int]:
    """Populate games, markets, users, real Warframe & Rust items, history, portfolio, and alerts."""
    existing_items = await session.scalar(select(func.count(ItemORM.id)))
    if if_empty and existing_items and existing_items > 0:
        logger.info("seed_skipped_non_empty", existing_items=existing_items)
        return {"items": int(existing_items), "snapshots": 0, "skipped": 1}

    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

    # 1. Games
    games_map: dict[str, GameORM] = {}
    for code, name in (("warframe", "Warframe"), ("rust", "Rust")):
        game = await session.scalar(select(GameORM).where(GameORM.code == code))
        if game is None:
            game = GameORM(name=name, code=code, is_active=True)
            session.add(game)
            await session.flush()
        games_map[code] = game

    # 2. Markets (2 per game for genuine M:N cross-market spread & multi-currency)
    market_defs = [
        (
            "wf_pc",
            "warframe",
            "Warframe.market (PC)",
            "https://api.warframe.market/v2",
            "PLT",
            Decimal("0.00"),
            15,
        ),
        (
            "wf_ps",
            "warframe",
            "Warframe.market (PS)",
            "https://api.warframe.market/v2",
            "PLT",
            Decimal("0.00"),
            15,
        ),
        (
            "skinport_rust",
            "rust",
            "Skinport (Rust EUR)",
            "https://api.skinport.com/v1/items",
            "EUR",
            Decimal("12.00"),
            15,
        ),
        (
            "rust_tm",
            "rust",
            "Rust.tm (USD)",
            "https://rust.tm/api/v2/prices/USD.json",
            "USD",
            Decimal("5.00"),
            15,
        ),
    ]
    markets_map: dict[str, MarketORM] = {}
    for code, game_code, name, url, cur, fee, sched in market_defs:
        m = await session.scalar(select(MarketORM).where(MarketORM.code == code))
        if m is None:
            m = MarketORM(
                game_id=games_map[game_code].id,
                name=name,
                code=code,
                base_url=url,
                currency=cur,
                fee_pct=fee,
                schedule_minutes=sched,
                is_active=True,
                last_collected_at=now,
            )
            session.add(m)
            await session.flush()
        markets_map[code] = m

    # 3. Demo Users for all roles
    users_map: dict[str, UserORM] = {}
    for uname, pwd, role in (
        ("admin", "admin123!", UserRole.ADMIN.value),
        ("analyst", "analyst123!", UserRole.ANALYST.value),
        ("trader", "trader123!", UserRole.USER.value),
    ):
        u = await session.scalar(select(UserORM).where(UserORM.username == uname))
        if u is None:
            u = UserORM(username=uname, password_hash=_hash_password(pwd), role=role)
            session.add(u)
            await session.flush()
        users_map[uname] = u

    # 4. Items + Historical PriceSnapshots across 2 markets per item
    wf_specs, rust_specs = _load_real_specs(
        now=now, days=days, max_items_per_game=max_items_per_game
    )
    catalog_by_game: list[tuple[str, list[_SeedItemSpec], tuple[MarketORM, MarketORM]]] = [
        ("warframe", wf_specs, (markets_map["wf_pc"], markets_map["wf_ps"])),
        ("rust", rust_specs, (markets_map["skinport_rust"], markets_map["rust_tm"])),
    ]

    snapshot_rows: list[dict[str, Any]] = []
    created_items: list[ItemORM] = []
    anomalies_to_create: list[AnomalyEventORM] = []

    for game_code, specs, (market_a, market_b) in catalog_by_game:
        game = games_map[game_code]
        for spec in specs:
            existing = await session.scalar(
                select(ItemORM).where(
                    ItemORM.game_id == game.id,
                    ItemORM.normalized_name == spec.normalized_name,
                )
            )
            if existing is not None:
                continue

            item = ItemORM(
                game_id=game.id,
                name=spec.name,
                name_en=spec.name_en,
                normalized_name=spec.normalized_name,
                item_type=spec.item_type,
                subcategory=spec.subcategory,
                base_item_shortname=spec.base_item_shortname,
                rarity=spec.rarity,
                external_id=spec.external_id,
                is_available=True,
                icon_url=spec.icon_url,
                description=spec.description,
                released_at=spec.released_at,
            )
            session.add(item)
            created_items.append(item)

        await session.flush()

        item_lookup = {it.normalized_name: it for it in created_items if it.game_id == game.id}

        for spec in specs:
            item_or_none = item_lookup.get(spec.normalized_name)
            if item_or_none is None:
                continue

            rng_seed = int(
                hashlib.sha256(f"hist:{game_code}:{spec.normalized_name}".encode()).hexdigest()[:8],
                16,
            )
            rng = random.Random(rng_seed)
            drift = rng.uniform(-0.0025, 0.0035)
            phase = rng.uniform(0, math.tau)
            market_b_premium = rng.uniform(1.03, 1.18)

            daily_usd_a: list[Decimal] = []
            daily_usd_b: list[Decimal] = []
            last_vol_a = spec.base_vol
            last_vol_b = max(2, int(spec.base_vol * rng.uniform(0.45, 0.85)))
            h_days = max(2, spec.history_days)

            for day_offset in range(h_days - 1, -1, -1):
                ts = now - timedelta(days=day_offset)
                t_idx = h_days - 1 - day_offset
                wave = 1.0 + 0.055 * math.sin(t_idx * 0.42 + phase) + drift * t_idx
                noise_a = rng.uniform(0.97, 1.03)
                noise_b = rng.uniform(0.97, 1.03)

                usd_a = max(0.20, spec.base_usd * wave * noise_a)
                if day_offset == 0 and spec.anomaly_spike != 0.0:
                    usd_a = max(0.20, usd_a * (1.0 + spec.anomaly_spike))

                usd_b = max(0.20, usd_a * market_b_premium * noise_b)
                if day_offset == 0 and spec.anomaly_spike != 0.0:
                    usd_b = max(0.20, spec.base_usd * wave * market_b_premium)

                vol_a = max(1, int(spec.base_vol * rng.uniform(0.7, 1.35)))
                vol_b = max(1, int(spec.base_vol * rng.uniform(0.35, 0.85)))
                last_vol_a, last_vol_b = vol_a, vol_b

                for market, usd_val, vol in (
                    (market_a, usd_a, vol_a),
                    (market_b, usd_b, vol_b),
                ):
                    if market.currency == "PLT":
                        orig_price = Decimal(
                            max(1, round(usd_val / float(plt_to_usd)))
                        ).quantize(_Q4)
                        rate = plt_to_usd
                        norm_price = convert_currency(orig_price, rate)
                    elif market.currency == "EUR":
                        orig_price = Decimal(
                            str(round(usd_val / float(eur_to_usd), 2))
                        ).quantize(_Q4)
                        rate = eur_to_usd
                        norm_price = convert_currency(orig_price, rate)
                    else:
                        orig_price = Decimal(str(round(usd_val, 2))).quantize(_Q4)
                        rate = Decimal("1.000000")
                        norm_price = orig_price

                    if market.id == market_a.id:
                        daily_usd_a.append(norm_price)
                    else:
                        daily_usd_b.append(norm_price)

                    snapshot_rows.append(
                        {
                            "item_id": item_or_none.id,
                            "market_id": market.id,
                            "original_price": orig_price,
                            "original_currency": market.currency,
                            "normalized_price": norm_price,
                            "exchange_rate": rate,
                            "volume": vol,
                            "collected_at": ts,
                            "last_checked_at": ts,
                        }
                    )

            last_a = daily_usd_a[-1]
            last_b = daily_usd_b[-1]
            prev_7 = daily_usd_a[-8:-1] if len(daily_usd_a) >= 8 else daily_usd_a[:-1]
            ma7 = (
                (sum(prev_7, Decimal("0")) / Decimal(len(prev_7))).quantize(
                    _Q4, rounding=ROUND_HALF_UP
                )
                if prev_7
                else last_a
            )
            min_p = min(last_a, last_b)
            max_p = max(last_a, last_b)
            spread = (
                (((max_p - min_p) / min_p) * Decimal("100")).quantize(_Q2, rounding=ROUND_HALF_UP)
                if min_p > Decimal("0")
                else Decimal("0.00")
            )
            p_24h = daily_usd_a[-2] if len(daily_usd_a) >= 2 else last_a
            p_7d = daily_usd_a[-8] if len(daily_usd_a) >= 8 else daily_usd_a[0]
            chg_24h = (((last_a - p_24h) / p_24h) * Decimal("100")).quantize(
                _Q2, rounding=ROUND_HALF_UP
            )
            chg_7d = (((last_a - p_7d) / p_7d) * Decimal("100")).quantize(
                _Q2, rounding=ROUND_HALF_UP
            )

            item_or_none.ma7_price = ma7
            item_or_none.latest_min_price = min_p
            item_or_none.latest_max_price = max_p
            item_or_none.latest_total_volume = last_vol_a + last_vol_b
            item_or_none.spread_pct = spread
            item_or_none.price_change_24h_pct = chg_24h
            item_or_none.price_change_7d_pct = chg_7d

            if spec.anomaly_spike != 0.0 and ma7 > Decimal("0"):
                dev = (((last_a - ma7) / ma7) * Decimal("100")).quantize(
                    _Q2, rounding=ROUND_HALF_UP
                )
                if abs(dev) > Decimal("20.00"):
                    anomalies_to_create.append(
                        AnomalyEventORM(
                            item_id=item_or_none.id,
                            market_id=market_a.id,
                            status=AnomalyStatus.OPEN.value,
                            ma7_price=ma7,
                            trigger_price=last_a,
                            deviation_pct=dev,
                            max_deviation_pct=dev,
                            opened_at=now - timedelta(hours=3),
                        )
                    )

    chunk_size = 1500
    for i in range(0, len(snapshot_rows), chunk_size):
        await session.execute(insert(PriceSnapshotORM), snapshot_rows[i : i + chunk_size])

    session.add_all(anomalies_to_create)

    if created_items:
        sample_wf = next(
            (it for it in created_items if it.game_id == games_map["warframe"].id),
            created_items[0],
        )
        sample_rust = next(
            (it for it in created_items if it.game_id == games_map["rust"].id),
            created_items[-1],
        )

        session.add(
            AnomalyEventORM(
                item_id=sample_rust.id,
                market_id=markets_map["skinport_rust"].id,
                status=AnomalyStatus.CLOSED.value,
                ma7_price=sample_rust.ma7_price or Decimal("10.0000"),
                trigger_price=(sample_rust.ma7_price or Decimal("10.0000")) * Decimal("1.26"),
                deviation_pct=Decimal("26.00"),
                max_deviation_pct=Decimal("28.40"),
                opened_at=now - timedelta(days=4),
                closed_at=now - timedelta(days=3, hours=14),
                closed_by_user_id=users_map["analyst"].id,
                comment="Підтверджено аналітиком: тимчасовий сплеск попиту після ігрового івенту.",
            )
        )

        wf_count = sum(1 for it in created_items if it.game_id == games_map["warframe"].id)
        rust_count = sum(1 for it in created_items if it.game_id == games_map["rust"].id)
        for m in markets_map.values():
            session.add(
                CollectionRunORM(
                    market_id=m.id,
                    status=CollectionStatus.SUCCESS.value,
                    started_at=now - timedelta(minutes=2),
                    finished_at=now - timedelta(minutes=1, seconds=48),
                    accepted_count=wf_count if m.game_id == games_map["warframe"].id else rust_count,
                    rejected_count=2,
                    new_snapshots_count=(
                        wf_count if m.game_id == games_map["warframe"].id else rust_count
                    ),
                    error_message=None,
                )
            )

        trader = users_map["trader"]
        demo_trades_spec = [
            (
                sample_rust,
                markets_map["skinport_rust"],
                TradeSide.BUY,
                2,
                Decimal("4.5000"),
                now - timedelta(days=12),
                "seed-trade-1",
            ),
            (
                sample_rust,
                markets_map["rust_tm"],
                TradeSide.SELL,
                1,
                Decimal("5.9000"),
                now - timedelta(days=4),
                "seed-trade-2",
            ),
            (
                sample_wf,
                markets_map["wf_pc"],
                TradeSide.BUY,
                5,
                Decimal("2.1000"),
                now - timedelta(days=9),
                "seed-trade-3",
            ),
        ]
        by_item: dict[int, list[TradeRecord]] = {}
        for idx_t, (it, mkt, side, qty, price, t_at, idem) in enumerate(demo_trades_spec, start=1):
            session.add(
                TradeORM(
                    user_id=trader.id,
                    item_id=it.id,
                    market_id=mkt.id,
                    side=side.value,
                    quantity=qty,
                    price=price,
                    traded_at=t_at,
                    idempotency_key=idem,
                )
            )
            by_item.setdefault(it.id, []).append(
                TradeRecord(
                    trade_id=idx_t,
                    side=side,
                    quantity=qty,
                    price=price,
                    traded_at=t_at,
                )
            )
        for item_id, records in by_item.items():
            pos_state = recalculate_position(records)
            session.add(
                PositionORM(
                    user_id=trader.id,
                    item_id=item_id,
                    quantity=pos_state.quantity,
                    avg_cost=pos_state.avg_cost,
                    realized_pnl=pos_state.realized_pnl,
                )
            )

        watch = WatchItemORM(
            user_id=trader.id,
            item_id=sample_wf.id,
            market_id=markets_map["wf_pc"].id,
            direction="below",
            threshold=(sample_wf.latest_min_price or Decimal("3.0000")) + Decimal("0.5000"),
            cooldown_minutes=60,
            last_alert_at=now - timedelta(hours=2),
        )
        session.add(watch)
        await session.flush()

        latest_snap = await session.scalar(
            select(PriceSnapshotORM)
            .where(
                PriceSnapshotORM.item_id == sample_wf.id,
                PriceSnapshotORM.market_id == markets_map["wf_pc"].id,
            )
            .order_by(PriceSnapshotORM.collected_at.desc())
            .limit(1)
        )
        if latest_snap is not None:
            session.add(
                AlertORM(
                    watch_item_id=watch.id,
                    user_id=trader.id,
                    snapshot_id=latest_snap.id,
                    triggered_price=latest_snap.normalized_price,
                    message=(
                        f"{sample_wf.name} опустився нижче порогу "
                        f"${watch.threshold:.2f} (зараз ${latest_snap.normalized_price:.2f})"
                    ),
                    is_read=False,
                )
            )

    await session.commit()
    logger.info(
        "seed_completed",
        items=len(created_items),
        snapshots=len(snapshot_rows),
        anomalies=len(anomalies_to_create) + 1,
    )
    return {
        "items": len(created_items),
        "snapshots": len(snapshot_rows),
        "anomalies": len(anomalies_to_create) + 1,
    }
