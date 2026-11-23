"""Market analytics: spreads, top gainers/losers, game liquidity index, rarity averages."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from econ_tracker.services.schemas import (
    AnalyticsOverviewResponse,
    GameIndexDTO,
    GameResponse,
    MoverItemDTO,
    RarityStatDTO,
    SpreadItemDTO,
)
from econ_tracker.storage.orm_models import GameORM, ItemORM, PriceSnapshotORM

_Q2 = Decimal("0.01")

class AnalyticsService:
    """Compute market reports directly via SQL aggregations and precomputed item metrics."""

    async def list_games_with_totals(self, session: AsyncSession) -> list[GameResponse]:
        """Return active/all games with item counts, offer counts, and total market value."""
        games = (await session.scalars(select(GameORM).order_by(GameORM.id.asc()))).all()
        agg_stmt = select(
            ItemORM.game_id,
            func.count(ItemORM.id),
            func.coalesce(func.sum(ItemORM.latest_total_volume), 0),
            func.coalesce(
                func.sum(
                    func.coalesce(ItemORM.latest_min_price, 0) * ItemORM.latest_total_volume
                ),
                0,
            ),
        ).group_by(ItemORM.game_id)
        agg_rows = {
            int(gid): (int(cnt), int(vol), Decimal(str(val)))
            for gid, cnt, vol, val in (await session.execute(agg_stmt)).all()
        }

        result: list[GameResponse] = []
        for g in games:
            cnt, vol, val = agg_rows.get(g.id, (0, 0, Decimal("0")))
            result.append(
                GameResponse(
                    id=g.id,
                    name=g.name,
                    code=g.code,
                    is_active=g.is_active,
                    items_count=cnt,
                    total_offers=vol,
                    total_market_value_usd=val.quantize(_Q2, rounding=ROUND_HALF_UP),
                )
            )
        return result

    async def get_spreads(
        self,
        session: AsyncSession,
        *,
        game: str | None = None,
        limit: int = 20,
    ) -> list[SpreadItemDTO]:
        """Return items with the largest current price gap across marketplaces."""
        stmt = (
            select(ItemORM)
            .join(GameORM, ItemORM.game_id == GameORM.id)
            .options(selectinload(ItemORM.game))
            .where(
                ItemORM.is_available.is_(True),
                ItemORM.spread_pct.is_not(None),
                ItemORM.latest_min_price.is_not(None),
                ItemORM.latest_max_price.is_not(None),
            )
            .order_by(ItemORM.spread_pct.desc(), ItemORM.id.asc())
            .limit(limit)
        )
        if game:
            stmt = stmt.where(GameORM.code == game.lower())

        items = (await session.scalars(stmt)).all()
        if not items:
            return []

        item_ids = [it.id for it in items]
        latest_sub = (
            select(
                PriceSnapshotORM.item_id,
                PriceSnapshotORM.market_id,
                func.max(PriceSnapshotORM.collected_at).label("max_ts"),
            )
            .where(PriceSnapshotORM.item_id.in_(item_ids))
            .group_by(PriceSnapshotORM.item_id, PriceSnapshotORM.market_id)
            .subquery()
        )
        snaps = (
            await session.scalars(
                select(PriceSnapshotORM)
                .options(selectinload(PriceSnapshotORM.market))
                .join(
                    latest_sub,
                    (PriceSnapshotORM.item_id == latest_sub.c.item_id)
                    & (PriceSnapshotORM.market_id == latest_sub.c.market_id)
                    & (PriceSnapshotORM.collected_at == latest_sub.c.max_ts),
                )
            )
        ).all()

        by_item: dict[int, list[PriceSnapshotORM]] = {}
        for s in snaps:
            by_item.setdefault(s.item_id, []).append(s)

        out: list[SpreadItemDTO] = []
        for it in items:
            item_snaps = sorted(by_item.get(it.id, []), key=lambda s: Decimal(s.normalized_price))
            min_p = Decimal(it.latest_min_price or 0)
            max_p = Decimal(it.latest_max_price or 0)
            cheapest_m = item_snaps[0].market.name if item_snaps else "N/A"
            priciest_m = item_snaps[-1].market.name if item_snaps else "N/A"
            out.append(
                SpreadItemDTO(
                    item_id=it.id,
                    name=it.name,
                    game_code=it.game.code if it.game else "",
                    min_price=min_p,
                    max_price=max_p,
                    spread_abs=(max_p - min_p).quantize(_Q2, rounding=ROUND_HALF_UP),
                    spread_pct=Decimal(it.spread_pct or 0),
                    cheapest_market=cheapest_m,
                    priciest_market=priciest_m,
                )
            )
        return out

    async def get_overview(
        self,
        session: AsyncSession,
        *,
        game: str | None = None,
    ) -> AnalyticsOverviewResponse:
        """Build full analytical report: indices, 24h/7d movers, rarity averages."""
        base_filter = select(ItemORM).join(GameORM, ItemORM.game_id == GameORM.id)
        if game:
            base_filter = base_filter.where(GameORM.code == game.lower())

        total_items = int(
            await session.scalar(select(func.count()).select_from(base_filter.subquery())) or 0
        )

        snap_stmt = select(func.count(PriceSnapshotORM.id))
        if game:
            snap_stmt = (
                snap_stmt.join(ItemORM, PriceSnapshotORM.item_id == ItemORM.id)
                .join(GameORM, ItemORM.game_id == GameORM.id)
                .where(GameORM.code == game.lower())
            )
        total_snapshots = int(await session.scalar(snap_stmt) or 0)

        games_stmt = select(GameORM).order_by(GameORM.id.asc())
        if game:
            games_stmt = games_stmt.where(GameORM.code == game.lower())
        games = (await session.scalars(games_stmt)).all()

        game_indices: list[GameIndexDTO] = []
        total_offers_all = 0
        total_val_all = Decimal("0.00")

        for g in games:
            g_totals = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(ItemORM.latest_total_volume), 0),
                        func.coalesce(
                            func.sum(
                                func.coalesce(ItemORM.latest_min_price, 0)
                                * ItemORM.latest_total_volume
                            ),
                            0,
                        ),
                    ).where(ItemORM.game_id == g.id)
                )
            ).one()
            g_offers = int(g_totals[0])
            g_val = Decimal(str(g_totals[1])).quantize(_Q2, rounding=ROUND_HALF_UP)
            total_offers_all += g_offers
            total_val_all += g_val

            liquid = (
                await session.scalars(
                    select(ItemORM)
                    .where(
                        ItemORM.game_id == g.id,
                        ItemORM.is_available.is_(True),
                        ItemORM.price_change_24h_pct.is_not(None),
                    )
                    .order_by(ItemORM.latest_total_volume.desc(), ItemORM.id.asc())
                    .limit(20)
                )
            ).all()

            if liquid:
                avg_24 = (
                    sum((Decimal(x.price_change_24h_pct or 0) for x in liquid), Decimal("0"))
                    / Decimal(len(liquid))
                ).quantize(_Q2, rounding=ROUND_HALF_UP)
                avg_7 = (
                    sum((Decimal(x.price_change_7d_pct or 0) for x in liquid), Decimal("0"))
                    / Decimal(len(liquid))
                ).quantize(_Q2, rounding=ROUND_HALF_UP)
            else:
                avg_24 = Decimal("0.00")
                avg_7 = Decimal("0.00")

            game_indices.append(
                GameIndexDTO(
                    game_code=g.code,
                    game_name=g.name,
                    liquid_items_count=len(liquid),
                    avg_change_24h_pct=avg_24,
                    avg_change_7d_pct=avg_7,
                    total_offers=g_offers,
                    total_market_value_usd=g_val,
                )
            )

        top_gainers_24h = await self._top_movers(session, game=game, window="24h", desc=True)
        top_losers_24h = await self._top_movers(session, game=game, window="24h", desc=False)
        top_gainers_7d = await self._top_movers(session, game=game, window="7d", desc=True)
        top_losers_7d = await self._top_movers(session, game=game, window="7d", desc=False)

        rarity_stmt = (
            select(
                ItemORM.rarity,
                func.count(ItemORM.id),
                func.coalesce(func.avg(ItemORM.latest_min_price), 0),
                func.coalesce(func.sum(ItemORM.latest_total_volume), 0),
            )
            .join(GameORM, ItemORM.game_id == GameORM.id)
            .group_by(ItemORM.rarity)
            .order_by(func.avg(ItemORM.latest_min_price).desc())
        )
        if game:
            rarity_stmt = rarity_stmt.where(GameORM.code == game.lower())

        rarity_stats = [
            RarityStatDTO(
                rarity=str(r),
                items_count=int(cnt),
                avg_price=Decimal(str(avg_p)).quantize(_Q2, rounding=ROUND_HALF_UP),
                total_volume=int(vol),
            )
            for r, cnt, avg_p, vol in (await session.execute(rarity_stmt)).all()
        ]

        return AnalyticsOverviewResponse(
            total_items=total_items,
            total_snapshots=total_snapshots,
            total_offers=total_offers_all,
            total_market_value_usd=total_val_all.quantize(_Q2, rounding=ROUND_HALF_UP),
            game_indices=game_indices,
            top_gainers_24h=top_gainers_24h,
            top_losers_24h=top_losers_24h,
            top_gainers_7d=top_gainers_7d,
            top_losers_7d=top_losers_7d,
            rarity_stats=rarity_stats,
        )

    async def _top_movers(
        self,
        session: AsyncSession,
        *,
        game: str | None,
        window: str,
        desc: bool,
        limit: int = 8,
    ) -> list[MoverItemDTO]:
        col = (
            ItemORM.price_change_24h_pct if window == "24h" else ItemORM.price_change_7d_pct
        )
        stmt = (
            select(ItemORM)
            .join(GameORM, ItemORM.game_id == GameORM.id)
            .options(selectinload(ItemORM.game))
            .where(col.is_not(None), ItemORM.latest_min_price.is_not(None))
            .order_by(col.desc() if desc else col.asc(), ItemORM.id.asc())
            .limit(limit)
        )
        if game:
            stmt = stmt.where(GameORM.code == game.lower())
        rows = (await session.scalars(stmt)).all()
        return [
            MoverItemDTO(
                item_id=it.id,
                name=it.name,
                game_code=it.game.code if it.game else "",
                item_type=it.item_type,
                rarity=it.rarity,
                current_price=Decimal(it.latest_min_price or 0),
                change_pct=Decimal(
                    (it.price_change_24h_pct if window == "24h" else it.price_change_7d_pct) or 0
                ),
                volume=it.latest_total_volume,
            )
            for it in rows
        ]
