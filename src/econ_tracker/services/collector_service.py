"""Concurrent fault-isolated data collector with lazy pipeline, alerts, and anomaly detection."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from econ_tracker.domain.enums import AnomalyStatus, CollectionStatus, WatchDirection
from econ_tracker.domain.exceptions import ExternalSourceError, ResourceNotFoundError
from econ_tracker.domain.logic import (
    evaluate_anomaly,
    should_create_snapshot,
    should_trigger_watch,
)
from econ_tracker.logging_config import get_logger
from econ_tracker.services.protocols import FxProviderProtocol, MarketSourceProtocol
from econ_tracker.services.schemas import CollectionRunResponse
from econ_tracker.sources.pipeline import PipelineStats, iter_validated_quotes
from econ_tracker.storage.orm_models import (
    AlertORM,
    AnomalyEventORM,
    CollectionRunORM,
    ItemORM,
    MarketORM,
    PriceSnapshotORM,
    WatchItemORM,
)

logger = get_logger(__name__)

_Q4 = Decimal("0.0001")
_Q2 = Decimal("0.01")

class CollectorService:
    """Orchestrate parallel collection, deduplication, precomputed MA-7, alerts, and anomalies."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        adapters: dict[str, MarketSourceProtocol],
        fx_provider: FxProviderProtocol,
        *,
        concurrency: int = 4,
        anomaly_threshold_pct: Decimal = Decimal("20.0"),
    ) -> None:
        self._session_factory = session_factory
        self._adapters = adapters
        self._fx_provider = fx_provider
        self._semaphore = asyncio.Semaphore(concurrency)
        self._anomaly_threshold_pct = anomaly_threshold_pct

    async def run_collection(
        self,
        *,
        market_id: int | None = None,
    ) -> list[CollectionRunResponse]:
        """Run collection for a single market or all active markets in parallel.

        A failure in one market is recorded in ``collection_runs`` and never aborts others.
        """
        async with self._session_factory() as session:
            stmt = select(MarketORM).options(selectinload(MarketORM.game))
            if market_id is not None:
                stmt = stmt.where(MarketORM.id == market_id)
            else:
                stmt = stmt.where(MarketORM.is_active.is_(True))
            markets = (await session.scalars(stmt.order_by(MarketORM.id.asc()))).all()
            if market_id is not None and not markets:
                raise ResourceNotFoundError(f"Market #{market_id} not found")
            market_ids = [m.id for m in markets]

        fx_rates = await self._fx_provider.get_rates_to_usd()

        tasks = [self._collect_single_market(mid, fx_rates) for mid in market_ids]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def _collect_single_market(
        self,
        market_id: int,
        fx_rates: dict[str, Decimal],
    ) -> CollectionRunResponse:
        async with self._semaphore, self._session_factory() as session:
            market = await session.scalar(
                select(MarketORM)
                .options(selectinload(MarketORM.game))
                .where(MarketORM.id == market_id)
            )
            assert market is not None

            started_at = datetime.now(UTC)
            run = CollectionRunORM(
                market_id=market.id,
                status=CollectionStatus.RUNNING.value,
                started_at=started_at,
            )
            session.add(run)
            await session.flush()

            adapter = self._adapters.get(market.code)
            if adapter is None:
                run.status = CollectionStatus.FAILED.value
                run.finished_at = datetime.now(UTC)
                run.error_message = f"No adapter registered for market '{market.code}'"
                await session.commit()
                return _to_run_response(run, market)

            rate_to_usd = fx_rates.get(market.currency.upper(), Decimal("1.000000"))
            stats = PipelineStats()
            new_snapshots = 0
            seen_item_ids: set[int] = set()
            touched_item_ids: set[int] = set()

            try:
                raw_iter = await adapter.fetch_quotes()

                for quote in iter_validated_quotes(raw_iter, rate_to_usd=rate_to_usd, stats=stats):
                    item = await session.scalar(
                        select(ItemORM).where(
                            ItemORM.game_id == market.game_id,
                            ItemORM.normalized_name == quote.normalized_name,
                        )
                    )
                    if item is None:
                        item = ItemORM(
                            game_id=market.game_id,
                            name=quote.name,
                            normalized_name=quote.normalized_name,
                            item_type=quote.item_type,
                            subcategory=quote.subcategory,
                            rarity=quote.rarity,
                            external_id=quote.external_id,
                            is_available=True,
                            icon_url=quote.icon_url,
                            description=quote.description,
                            released_at=quote.released_at,
                        )
                        session.add(item)
                        await session.flush()
                    else:
                        item.is_available = True
                        if quote.icon_url and not item.icon_url:
                            item.icon_url = quote.icon_url
                        if quote.description and not item.description:
                            item.description = quote.description
                        if quote.released_at and not item.released_at:
                            item.released_at = quote.released_at

                    seen_item_ids.add(item.id)

                    last_snap = await session.scalar(
                        select(PriceSnapshotORM)
                        .where(
                            PriceSnapshotORM.item_id == item.id,
                            PriceSnapshotORM.market_id == market.id,
                        )
                        .order_by(PriceSnapshotORM.collected_at.desc(), PriceSnapshotORM.id.desc())
                        .limit(1)
                    )

                    prev_price = Decimal(last_snap.normalized_price) if last_snap else None
                    prev_vol = last_snap.volume if last_snap else None

                    if should_create_snapshot(
                        prev_price, prev_vol, quote.normalized_price, quote.volume
                    ):
                        snap = PriceSnapshotORM(
                            item_id=item.id,
                            market_id=market.id,
                            original_price=quote.original_price,
                            original_currency=quote.original_currency,
                            normalized_price=quote.normalized_price,
                            exchange_rate=quote.exchange_rate,
                            volume=quote.volume,
                            collected_at=quote.collected_at,
                            last_checked_at=quote.collected_at,
                        )
                        session.add(snap)
                        await session.flush()
                        new_snapshots += 1
                        touched_item_ids.add(item.id)

                        await self._evaluate_watches(
                            session,
                            item=item,
                            market=market,
                            snapshot=snap,
                            previous_price=prev_price,
                        )
                        await self._evaluate_item_anomaly(
                            session,
                            item=item,
                            market=market,
                            current_price=quote.normalized_price,
                            now=quote.collected_at,
                        )
                    elif last_snap is not None:
                        last_snap.last_checked_at = quote.collected_at

                await self._mark_disappeared_items(
                    session,
                    market=market,
                    seen_item_ids=seen_item_ids,
                )

                for iid in touched_item_ids:
                    await self._refresh_item_metrics(session, iid)

                market.last_collected_at = datetime.now(UTC)
                run.accepted_count = stats.accepted
                run.rejected_count = stats.rejected
                run.new_snapshots_count = new_snapshots
                run.finished_at = datetime.now(UTC)
                run.status = (
                    CollectionStatus.PARTIAL.value
                    if stats.rejected > 0 and stats.accepted > 0
                    else CollectionStatus.SUCCESS.value
                )
                await session.commit()
                logger.info(
                    "market_collection_finished",
                    market=market.code,
                    accepted=stats.accepted,
                    rejected=stats.rejected,
                    new_snapshots=new_snapshots,
                )
            except ExternalSourceError as exc:
                run.status = CollectionStatus.FAILED.value
                run.finished_at = datetime.now(UTC)
                run.accepted_count = stats.accepted
                run.rejected_count = stats.rejected
                run.new_snapshots_count = new_snapshots
                run.error_message = exc.detail
                await session.commit()
                logger.error("market_collection_failed", market=market.code, error=exc.detail)
            except Exception as exc:
                run.status = CollectionStatus.FAILED.value
                run.finished_at = datetime.now(UTC)
                run.error_message = f"Unexpected error: {exc}"
                await session.commit()
                logger.exception("market_collection_unexpected_error", market=market.code)

            return _to_run_response(run, market)

    async def _evaluate_watches(
        self,
        session: AsyncSession,
        *,
        item: ItemORM,
        market: MarketORM,
        snapshot: PriceSnapshotORM,
        previous_price: Decimal | None,
    ) -> None:
        watches = (
            await session.scalars(
                select(WatchItemORM).where(
                    WatchItemORM.item_id == item.id,
                    WatchItemORM.market_id == market.id,
                )
            )
        ).all()
        now = _ensure_utc(snapshot.collected_at)
        for watch in watches:
            last_alert_at = _ensure_utc(watch.last_alert_at) if watch.last_alert_at else None
            if not should_trigger_watch(
                direction=WatchDirection(watch.direction),
                threshold=Decimal(watch.threshold),
                current_price=Decimal(snapshot.normalized_price),
                previous_price=previous_price,
                last_alert_at=last_alert_at,
                cooldown_minutes=watch.cooldown_minutes,
                now=now,
            ):
                continue

            exists = await session.scalar(
                select(AlertORM.id).where(
                    AlertORM.watch_item_id == watch.id,
                    AlertORM.snapshot_id == snapshot.id,
                )
            )
            if exists is not None:
                continue

            alert = AlertORM(
                watch_item_id=watch.id,
                user_id=watch.user_id,
                snapshot_id=snapshot.id,
                triggered_price=snapshot.normalized_price,
                message=(
                    f"{item.name} on {market.name} crossed {watch.direction} "
                    f"${watch.threshold:.2f} (current ${snapshot.normalized_price:.2f})"
                ),
                is_read=False,
            )
            session.add(alert)
            watch.last_alert_at = now

    async def _evaluate_item_anomaly(
        self,
        session: AsyncSession,
        *,
        item: ItemORM,
        market: MarketORM,
        current_price: Decimal,
        now: datetime,
    ) -> None:
        ma7 = Decimal(item.ma7_price) if item.ma7_price is not None else None
        open_event = await session.scalar(
            select(AnomalyEventORM)
            .where(
                AnomalyEventORM.item_id == item.id,
                AnomalyEventORM.market_id == market.id,
                AnomalyEventORM.status == AnomalyStatus.OPEN.value,
            )
            .limit(1)
        )
        decision = evaluate_anomaly(
            current_price=current_price,
            ma7_price=ma7,
            threshold_pct=self._anomaly_threshold_pct,
            has_open_event=open_event is not None,
            existing_max_deviation=(
                Decimal(open_event.max_deviation_pct) if open_event is not None else None
            ),
        )
        if decision.action == "open" and ma7 is not None:
            session.add(
                AnomalyEventORM(
                    item_id=item.id,
                    market_id=market.id,
                    status=AnomalyStatus.OPEN.value,
                    ma7_price=ma7,
                    trigger_price=current_price,
                    deviation_pct=decision.deviation_pct,
                    max_deviation_pct=decision.max_deviation_pct,
                    opened_at=now,
                )
            )
        elif decision.action == "update" and open_event is not None:
            open_event.deviation_pct = decision.deviation_pct
            open_event.max_deviation_pct = decision.max_deviation_pct
        elif decision.action == "close" and open_event is not None:
            open_event.status = AnomalyStatus.CLOSED.value
            open_event.closed_at = now
            open_event.comment = "Auto-closed: price returned within normal MA-7 band."

    async def _mark_disappeared_items(
        self,
        session: AsyncSession,
        *,
        market: MarketORM,
        seen_item_ids: set[int],
    ) -> None:
        """Mark items unavailable only if this market had previously listed items and scraped ok."""
        if not seen_item_ids:
            return
        known_ids = set(
            (
                await session.scalars(
                    select(PriceSnapshotORM.item_id)
                    .where(PriceSnapshotORM.market_id == market.id)
                    .distinct()
                )
            ).all()
        )
        if len(known_ids) > 0 and len(seen_item_ids) >= int(len(known_ids) * 0.5):
            missing_ids = known_ids - seen_item_ids
            if missing_ids:
                missing_items = (
                    await session.scalars(select(ItemORM).where(ItemORM.id.in_(missing_ids)))
                ).all()
                for it in missing_items:
                    other_recent = await session.scalar(
                        select(PriceSnapshotORM.id)
                        .where(
                            PriceSnapshotORM.item_id == it.id,
                            PriceSnapshotORM.market_id != market.id,
                            PriceSnapshotORM.last_checked_at
                            >= datetime.now(UTC) - timedelta(hours=24),
                        )
                        .limit(1)
                    )
                    if other_recent is None:
                        it.is_available = False

    async def _refresh_item_metrics(self, session: AsyncSession, item_id: int) -> None:
        item = await session.get(ItemORM, item_id)
        if item is None:
            return

        now = datetime.now(UTC)
        avg_7d = await session.scalar(
            select(func.avg(PriceSnapshotORM.normalized_price)).where(
                PriceSnapshotORM.item_id == item_id,
                PriceSnapshotORM.collected_at >= now - timedelta(days=7),
            )
        )
        if avg_7d is not None:
            item.ma7_price = Decimal(str(avg_7d)).quantize(_Q4, rounding=ROUND_HALF_UP)

        latest_sub = (
            select(
                PriceSnapshotORM.market_id,
                func.max(PriceSnapshotORM.collected_at).label("max_ts"),
            )
            .where(PriceSnapshotORM.item_id == item_id)
            .group_by(PriceSnapshotORM.market_id)
            .subquery()
        )
        latest_snaps = (
            await session.scalars(
                select(PriceSnapshotORM)
                .join(
                    latest_sub,
                    (PriceSnapshotORM.market_id == latest_sub.c.market_id)
                    & (PriceSnapshotORM.collected_at == latest_sub.c.max_ts),
                )
                .where(PriceSnapshotORM.item_id == item_id)
            )
        ).all()

        if latest_snaps:
            prices = [Decimal(s.normalized_price) for s in latest_snaps]
            min_p = min(prices)
            max_p = max(prices)
            item.latest_min_price = min_p
            item.latest_max_price = max_p
            item.latest_total_volume = sum(s.volume for s in latest_snaps)
            if min_p > Decimal("0"):
                item.spread_pct = (((max_p - min_p) / min_p) * Decimal("100")).quantize(
                    _Q2, rounding=ROUND_HALF_UP
                )

def _ensure_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)

def _to_run_response(run: CollectionRunORM, market: MarketORM) -> CollectionRunResponse:
    return CollectionRunResponse(
        id=run.id,
        market_id=run.market_id,
        market_code=market.code,
        market_name=market.name,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        accepted_count=run.accepted_count,
        rejected_count=run.rejected_count,
        new_snapshots_count=run.new_snapshots_count,
        error_message=run.error_message,
    )
