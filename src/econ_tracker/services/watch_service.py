"""Watchlist and Alert notification service."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from econ_tracker.domain.enums import WatchDirection
from econ_tracker.domain.exceptions import ResourceNotFoundError
from econ_tracker.services.schemas import (
    AlertResponse,
    WatchCreateRequest,
    WatchItemResponse,
    WatchUpdateRequest,
)
from econ_tracker.storage.orm_models import AlertORM, ItemORM, MarketORM, WatchItemORM

_Q4 = Decimal("0.0001")


class WatchService:
    """Manage per-user item price watches and unread alerts."""

    async def create_or_get_watch(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        payload: WatchCreateRequest,
    ) -> tuple[WatchItemResponse, bool]:
        """Create watch rule; duplicate (user, item, market) returns existing without error."""
        item = await session.get(ItemORM, payload.item_id)
        if item is None:
            raise ResourceNotFoundError(f"Item #{payload.item_id} not found")
        market = await session.get(MarketORM, payload.market_id)
        if market is None:
            raise ResourceNotFoundError(f"Market #{payload.market_id} not found")

        existing = await session.scalar(
            select(WatchItemORM)
            .options(
                selectinload(WatchItemORM.item).selectinload(ItemORM.game),
                selectinload(WatchItemORM.market),
            )
            .where(
                WatchItemORM.user_id == user_id,
                WatchItemORM.item_id == payload.item_id,
                WatchItemORM.market_id == payload.market_id,
            )
        )
        if existing is not None:
            return _to_watch_response(existing), False

        watch = WatchItemORM(
            user_id=user_id,
            item_id=payload.item_id,
            market_id=payload.market_id,
            direction=payload.direction.value,
            threshold=payload.threshold.quantize(_Q4, rounding=ROUND_HALF_UP),
            cooldown_minutes=payload.cooldown_minutes,
        )
        session.add(watch)
        await session.commit()

        loaded = await self._load_watch(session, watch.id, user_id)
        return _to_watch_response(loaded), True

    async def list_watches(
        self,
        session: AsyncSession,
        *,
        user_id: int,
    ) -> list[WatchItemResponse]:
        stmt = (
            select(WatchItemORM)
            .options(
                selectinload(WatchItemORM.item).selectinload(ItemORM.game),
                selectinload(WatchItemORM.market),
            )
            .where(WatchItemORM.user_id == user_id)
            .order_by(WatchItemORM.created_at.desc())
        )
        rows = (await session.scalars(stmt)).all()
        return [_to_watch_response(r) for r in rows]

    async def update_watch(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        watch_id: int,
        payload: WatchUpdateRequest,
    ) -> WatchItemResponse:
        watch = await self._load_watch(session, watch_id, user_id)
        if payload.threshold is not None:
            watch.threshold = payload.threshold.quantize(_Q4, rounding=ROUND_HALF_UP)
        if payload.direction is not None:
            watch.direction = payload.direction.value
        if payload.cooldown_minutes is not None:
            watch.cooldown_minutes = payload.cooldown_minutes
        await session.commit()
        loaded = await self._load_watch(session, watch.id, user_id)
        return _to_watch_response(loaded)

    async def delete_watch(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        watch_id: int,
    ) -> None:
        watch = await self._load_watch(session, watch_id, user_id)
        await session.delete(watch)
        await session.commit()

    async def list_alerts(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        unread_only: bool = False,
    ) -> list[AlertResponse]:
        stmt = (
            select(AlertORM)
            .where(AlertORM.user_id == user_id)
            .order_by(AlertORM.created_at.desc())
            .limit(200)
        )
        if unread_only:
            stmt = stmt.where(AlertORM.is_read.is_(False))
        rows = (await session.scalars(stmt)).all()
        return [_to_alert_response(r) for r in rows]

    async def mark_alert_read(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        alert_id: int,
    ) -> AlertResponse:
        alert = await session.scalar(
            select(AlertORM).where(AlertORM.id == alert_id, AlertORM.user_id == user_id)
        )
        if alert is None:
            raise ResourceNotFoundError(f"Alert #{alert_id} not found")
        alert.is_read = True
        await session.commit()
        await session.refresh(alert)
        return _to_alert_response(alert)

    async def _load_watch(
        self,
        session: AsyncSession,
        watch_id: int,
        user_id: int,
    ) -> WatchItemORM:
        stmt = (
            select(WatchItemORM)
            .options(
                selectinload(WatchItemORM.item).selectinload(ItemORM.game),
                selectinload(WatchItemORM.market),
            )
            .where(WatchItemORM.id == watch_id, WatchItemORM.user_id == user_id)
        )
        watch = await session.scalar(stmt)
        if watch is None:
            raise ResourceNotFoundError(f"Watch rule #{watch_id} not found")
        return watch


def _to_watch_response(w: WatchItemORM) -> WatchItemResponse:
    return WatchItemResponse(
        id=w.id,
        item_id=w.item_id,
        item_name=w.item.name if w.item else "",
        game_code=w.item.game.code if w.item and w.item.game else "",
        market_id=w.market_id,
        market_name=w.market.name if w.market else "",
        direction=WatchDirection(w.direction),
        threshold=Decimal(w.threshold),
        cooldown_minutes=w.cooldown_minutes,
        last_alert_at=w.last_alert_at,
        created_at=w.created_at,
    )


def _to_alert_response(a: AlertORM) -> AlertResponse:
    return AlertResponse(
        id=a.id,
        watch_item_id=a.watch_item_id,
        snapshot_id=a.snapshot_id,
        triggered_price=Decimal(a.triggered_price),
        message=a.message,
        is_read=a.is_read,
        created_at=a.created_at,
    )
