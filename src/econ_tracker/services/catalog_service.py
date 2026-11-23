"""Catalog search, category/subcategory facets, item cards, aggregated history & CSV export."""

from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from econ_tracker.domain.enums import HistoryStep
from econ_tracker.domain.exceptions import ResourceNotFoundError
from econ_tracker.services.schemas import (
    CategoryFacet,
    ItemDetailResponse,
    ItemSortOption,
    ItemSummaryResponse,
    MarketQuoteDTO,
    PaginatedItemsResponse,
    PriceHistoryPoint,
    PriceHistoryResponse,
    SubcategoryFacet,
)
from econ_tracker.storage.orm_models import GameORM, ItemORM, MarketORM, PriceSnapshotORM

_Q4 = Decimal("0.0001")
_Q2 = Decimal("0.01")

CATEGORY_LABELS: dict[str, str] = {
    # Rust
    "clothing": "Одежда и броня",
    "weapons": "Оружие",
    "deployables": "Постройки и двери",
    "tools": "Инструменты",
    # Warframe
    "warframes": "Варфреймы",
    "mods": "Моды",
    "arcanes": "Мистификаторы",
    "relics": "Реликвии",
    "companions": "Компаньоны",
    "other": "Прочее",
}

SUBCATEGORY_LABELS: dict[str, str] = {
    # Rust clothing
    "hoodie": "Худи",
    "pants": "Штаны",
    "facemask": "Металл. маска",
    "chestplate": "Нагрудник",
    "kilt": "Килт",
    "jacket": "Куртка",
    "gloves": "Перчатки",
    "boots": "Ботинки",
    "headgear": "Головной убор",
    "shirt": "Футболка",
    "hazmat": "Хазмат",
    # Rust weapons
    "ak47": "AK-47",
    "mp5": "MP5A4",
    "lr300": "LR-300",
    "thompson": "Томпсон",
    "sar": "Полуавтомат (SAR)",
    "sniper": "Винтовка (Bolt)",
    "shotgun": "Дробовик",
    "pistol": "Пистолет / Револьвер",
    "custom_smg": "Custom SMG",
    "heavy": "Тяжёлое",
    "bow": "Лук / Арбалет",
    "melee": "Ближний бой",
    # Rust deployables & tools
    "furnace": "Печка",
    "garage_door": "Гаражная дверь",
    "sheet_metal_door": "Металл. дверь",
    "armored_door": "Бронир. дверь",
    "storage_box": "Большой ящик",
    "sleeping_bag": "Спальник",
    "base_decor": "Интерьер базы",
    "hatchet": "Топор",
    "pickaxe": "Кирка",
    "rock": "Камень",
    "hammer": "Киянка",
    "raiding": "Рейд-заряды",
    # Warframe
    "prime_set": "Prime Сет",
    "blueprint": "Чертёж",
    "primary": "Основное",
    "secondary": "Вторичное",
    "mod": "Мод",
    "aura": "Аура",
    "stance": "Стойка",
    "augment": "Аугмент",
    "arcane": "Мистификатор",
    "void_relic": "Реликвия Бездны",
    "weapon_set": "Оружейный сет",
    "weapon_part": "Компонент оружия",
    "companion": "Страж / Компаньон",
    "misc": "Другое",
    "general": "Общее",
}


class CatalogService:
    """Server-side filtering, pagination, category facets, and price history aggregation."""

    async def list_items(
        self,
        session: AsyncSession,
        *,
        q: str | None = None,
        game: str | None = None,
        item_type: str | None = None,
        subcategory: str | None = None,
        rarity: str | None = None,
        market: str | None = None,
        price_min: Decimal | None = None,
        price_max: Decimal | None = None,
        available_only: bool = False,
        sort: ItemSortOption = "volume_desc",
        page: int = 1,
        page_size: int = 24,
    ) -> PaginatedItemsResponse:
        """Query items with server-side filters, deterministic sorting, and pagination."""
        stmt = select(ItemORM).join(GameORM, ItemORM.game_id == GameORM.id)

        if q:
            pattern = f"%{q.strip().lower()}%"
            stmt = stmt.where(func.lower(ItemORM.name).like(pattern))
        if game:
            stmt = stmt.where(GameORM.code == game.lower())
        if item_type:
            stmt = stmt.where(ItemORM.item_type == item_type.lower())
        if subcategory:
            stmt = stmt.where(ItemORM.subcategory == subcategory.lower())
        if rarity:
            stmt = stmt.where(ItemORM.rarity == rarity.lower())
        if available_only:
            stmt = stmt.where(ItemORM.is_available.is_(True))
        if price_min is not None:
            stmt = stmt.where(ItemORM.latest_min_price >= price_min)
        if price_max is not None:
            stmt = stmt.where(ItemORM.latest_min_price <= price_max)
        if market:
            subq = (
                select(PriceSnapshotORM.item_id)
                .join(MarketORM, PriceSnapshotORM.market_id == MarketORM.id)
                .where(MarketORM.code == market.lower())
                .distinct()
            )
            stmt = stmt.where(ItemORM.id.in_(subq))

        total = int(
            await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )

        # Deterministic sorting with tie-breaker ItemORM.id ASC (prevents pagination drift)
        order_map: dict[ItemSortOption, list[Any]] = {
            "price_asc": [ItemORM.latest_min_price.asc().nulls_last(), ItemORM.id.asc()],
            "price_desc": [ItemORM.latest_min_price.desc().nulls_last(), ItemORM.id.asc()],
            "volume_desc": [ItemORM.latest_total_volume.desc(), ItemORM.id.asc()],
            "spread_desc": [ItemORM.spread_pct.desc().nulls_last(), ItemORM.id.asc()],
            "change_desc": [ItemORM.price_change_24h_pct.desc().nulls_last(), ItemORM.id.asc()],
            "name_asc": [ItemORM.name.asc(), ItemORM.id.asc()],
        }
        order_clauses = order_map.get(sort, order_map["volume_desc"])

        offset = (page - 1) * page_size
        paged_stmt = (
            stmt.options(selectinload(ItemORM.game))
            .order_by(*order_clauses)
            .offset(offset)
            .limit(page_size)
        )
        rows = (await session.scalars(paged_stmt)).all()
        pages = max(1, math.ceil(total / page_size)) if total > 0 else 1

        return PaginatedItemsResponse(
            items=[_to_item_summary(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def get_category_facets(
        self,
        session: AsyncSession,
        *,
        game: str | None = None,
    ) -> list[CategoryFacet]:
        """Return category -> subcategory hierarchy with item counts and offer volumes."""
        stmt = (
            select(
                ItemORM.item_type,
                ItemORM.subcategory,
                func.count(ItemORM.id).label("cnt"),
                func.coalesce(func.sum(ItemORM.latest_total_volume), 0).label("vol"),
            )
            .join(GameORM, ItemORM.game_id == GameORM.id)
            .group_by(ItemORM.item_type, ItemORM.subcategory)
        )
        if game:
            stmt = stmt.where(GameORM.code == game.lower())

        rows = (await session.execute(stmt)).all()
        grouped: dict[str, list[SubcategoryFacet]] = defaultdict(list)
        cat_totals: dict[str, tuple[int, int]] = {}

        for item_type, subcat, cnt, vol in rows:
            cnt_i, vol_i = int(cnt), int(vol)
            sub_code = str(subcat)
            sub_label = SUBCATEGORY_LABELS.get(sub_code, sub_code.replace("_", " ").title())
            grouped[str(item_type)].append(
                SubcategoryFacet(
                    code=sub_code,
                    label=sub_label,
                    items_count=cnt_i,
                    total_volume=vol_i,
                )
            )
            prev_c, prev_v = cat_totals.get(str(item_type), (0, 0))
            cat_totals[str(item_type)] = (prev_c + cnt_i, prev_v + vol_i)

        facets: list[CategoryFacet] = []
        for cat_code, subs in sorted(
            grouped.items(), key=lambda kv: cat_totals[kv[0]][0], reverse=True
        ):
            subs.sort(key=lambda s: s.items_count, reverse=True)
            c_cnt, c_vol = cat_totals[cat_code]
            facets.append(
                CategoryFacet(
                    code=cat_code,
                    label=CATEGORY_LABELS.get(cat_code, cat_code.title()),
                    items_count=c_cnt,
                    total_volume=c_vol,
                    subcategories=subs,
                )
            )
        return facets

    async def get_item_detail(
        self,
        session: AsyncSession,
        *,
        item_id: int,
    ) -> ItemDetailResponse:
        """Return item card with latest quotes on every market and cross-market spread."""
        item = await session.scalar(
            select(ItemORM).options(selectinload(ItemORM.game)).where(ItemORM.id == item_id)
        )
        if item is None:
            raise ResourceNotFoundError(f"Item #{item_id} not found")

        # Subquery: latest snapshot timestamp per market for this item
        latest_sub = (
            select(
                PriceSnapshotORM.market_id,
                func.max(PriceSnapshotORM.collected_at).label("max_ts"),
            )
            .where(PriceSnapshotORM.item_id == item_id)
            .group_by(PriceSnapshotORM.market_id)
            .subquery()
        )
        snaps_stmt = (
            select(PriceSnapshotORM)
            .options(selectinload(PriceSnapshotORM.market))
            .join(
                latest_sub,
                (PriceSnapshotORM.market_id == latest_sub.c.market_id)
                & (PriceSnapshotORM.collected_at == latest_sub.c.max_ts),
            )
            .where(PriceSnapshotORM.item_id == item_id)
            .order_by(PriceSnapshotORM.normalized_price.asc())
        )
        snaps = (await session.scalars(snaps_stmt)).all()

        # Deduplicate in case two snapshots share exact same timestamp
        seen_markets: set[int] = set()
        quotes: list[MarketQuoteDTO] = []
        for snap in snaps:
            if snap.market_id in seen_markets:
                continue
            seen_markets.add(snap.market_id)
            quotes.append(
                MarketQuoteDTO(
                    market_id=snap.market_id,
                    market_code=snap.market.code,
                    market_name=snap.market.name,
                    original_price=Decimal(snap.original_price),
                    original_currency=snap.original_currency,
                    normalized_price=Decimal(snap.normalized_price),
                    exchange_rate=Decimal(snap.exchange_rate),
                    volume=snap.volume,
                    collected_at=snap.collected_at,
                    last_checked_at=snap.last_checked_at,
                )
            )

        cheapest = quotes[0].normalized_price if quotes else None
        priciest = quotes[-1].normalized_price if quotes else None
        spread_abs = (
            (priciest - cheapest).quantize(_Q4, rounding=ROUND_HALF_UP)
            if cheapest is not None and priciest is not None
            else None
        )

        summary = _to_item_summary(item)
        return ItemDetailResponse(
            **summary.model_dump(),
            markets=quotes,
            cheapest_price=cheapest,
            most_expensive_price=priciest,
            spread_abs=spread_abs,
        )

    async def get_price_history(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        step: HistoryStep = HistoryStep.DAY,
        market_id: int | None = None,
    ) -> PriceHistoryResponse:
        """Aggregate historical prices (min, max, avg, median) & volume by hour/day/week."""
        item = await session.get(ItemORM, item_id)
        if item is None:
            raise ResourceNotFoundError(f"Item #{item_id} not found")

        now = datetime.now(UTC)
        dt_from = date_from or (now - timedelta(days=30))
        dt_to = date_to or now

        stmt = (
            select(
                PriceSnapshotORM.collected_at,
                PriceSnapshotORM.normalized_price,
                PriceSnapshotORM.volume,
            )
            .where(
                PriceSnapshotORM.item_id == item_id,
                PriceSnapshotORM.collected_at >= dt_from,
                PriceSnapshotORM.collected_at <= dt_to,
            )
            .order_by(PriceSnapshotORM.collected_at.asc())
        )
        if market_id is not None:
            stmt = stmt.where(PriceSnapshotORM.market_id == market_id)

        rows = (await session.execute(stmt)).all()

        buckets: dict[datetime, tuple[list[Decimal], list[int]]] = defaultdict(lambda: ([], []))
        for collected_at, price, vol in rows:
            ts = (
                collected_at
                if collected_at.tzinfo is not None
                else collected_at.replace(tzinfo=UTC)
            )
            bucket_dt = _floor_bucket(ts, step)
            buckets[bucket_dt][0].append(Decimal(price))
            buckets[bucket_dt][1].append(int(vol))

        points: list[PriceHistoryPoint] = []
        for bucket_dt in sorted(buckets.keys()):
            prices, vols = buckets[bucket_dt]
            avg_p = (sum(prices, Decimal("0")) / Decimal(len(prices))).quantize(
                _Q4, rounding=ROUND_HALF_UP
            )
            med_p = Decimal(str(median(prices))).quantize(_Q4, rounding=ROUND_HALF_UP)
            points.append(
                PriceHistoryPoint(
                    bucket=bucket_dt,
                    min_price=min(prices).quantize(_Q4, rounding=ROUND_HALF_UP),
                    max_price=max(prices).quantize(_Q4, rounding=ROUND_HALF_UP),
                    avg_price=avg_p,
                    median_price=med_p,
                    avg_volume=round(sum(vols) / len(vols)),
                    snapshots_count=len(prices),
                )
            )

        return PriceHistoryResponse(
            item_id=item.id,
            item_name=item.name,
            step=step,
            points=points,
        )

    def render_history_csv(self, history: PriceHistoryResponse) -> str:
        """Render aggregated price history table as RFC 4180 CSV."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "bucket_utc",
                "min_price_usd",
                "max_price_usd",
                "avg_price_usd",
                "median_price_usd",
                "avg_volume",
                "snapshots_count",
            ]
        )
        for pt in history.points:
            writer.writerow(
                [
                    pt.bucket.isoformat(),
                    f"{pt.min_price:.4f}",
                    f"{pt.max_price:.4f}",
                    f"{pt.avg_price:.4f}",
                    f"{pt.median_price:.4f}",
                    pt.avg_volume,
                    pt.snapshots_count,
                ]
            )
        return buf.getvalue()


def _floor_bucket(dt: datetime, step: HistoryStep) -> datetime:
    if step == HistoryStep.HOUR:
        return dt.replace(minute=0, second=0, microsecond=0)
    if step == HistoryStep.DAY:
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    # WEEK: Monday 00:00 UTC
    monday = dt - timedelta(days=dt.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def _to_item_summary(item: ItemORM) -> ItemSummaryResponse:
    return ItemSummaryResponse(
        id=item.id,
        game_id=item.game_id,
        game_code=item.game.code if item.game else "",
        name=item.name,
        normalized_name=item.normalized_name,
        item_type=item.item_type,
        subcategory=item.subcategory,
        rarity=item.rarity,
        external_id=item.external_id,
        is_available=item.is_available,
        icon_url=item.icon_url,
        description=item.description,
        released_at=item.released_at,
        ma7_price=Decimal(item.ma7_price) if item.ma7_price is not None else None,
        latest_min_price=(
            Decimal(item.latest_min_price) if item.latest_min_price is not None else None
        ),
        latest_max_price=(
            Decimal(item.latest_max_price) if item.latest_max_price is not None else None
        ),
        latest_total_volume=item.latest_total_volume,
        spread_pct=Decimal(item.spread_pct) if item.spread_pct is not None else None,
        price_change_24h_pct=(
            Decimal(item.price_change_24h_pct)
            if item.price_change_24h_pct is not None
            else None
        ),
        price_change_7d_pct=(
            Decimal(item.price_change_7d_pct) if item.price_change_7d_pct is not None else None
        ),
    )
