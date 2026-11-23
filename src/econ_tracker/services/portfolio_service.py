"""Transactional portfolio & trade service (KEY STATE-CHANGING OPERATION)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from econ_tracker.domain.enums import TradeSide
from econ_tracker.domain.exceptions import ResourceNotFoundError
from econ_tracker.domain.logic import recalculate_position
from econ_tracker.domain.models import TradeRecord
from econ_tracker.logging_config import get_logger
from econ_tracker.services.schemas import (
    PortfolioSummaryResponse,
    PositionResponse,
    TradeCreateRequest,
    TradeResponse,
)
from econ_tracker.storage.orm_models import (
    ItemORM,
    MarketORM,
    PositionORM,
    TradeORM,
)

logger = get_logger(__name__)

_Q4 = Decimal("0.0001")
_Q2 = Decimal("0.01")


class PortfolioService:
    """Manage user trades and positions with transactional locking & idempotency."""

    def __init__(self) -> None:
        # In-process lock complements PostgreSQL SELECT ... FOR UPDATE on SQLite/single-node
        self._position_locks: dict[tuple[int, int], asyncio.Lock] = {}

    def _get_lock(self, user_id: int, item_id: int) -> asyncio.Lock:
        key = (user_id, item_id)
        lock = self._position_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._position_locks[key] = lock
        return lock

    async def create_trade(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        payload: TradeCreateRequest,
    ) -> tuple[TradeResponse, bool]:
        """Register a buy/sell trade and atomically recalculate the user's position.

        Returns ``(TradeResponse, created)`` where ``created=False`` means an existing
        trade was returned idempotently for the same ``idempotency_key``.
        """
        idem_key = payload.idempotency_key or str(uuid.uuid4())
        lock = self._get_lock(user_id, payload.item_id)

        async with lock:
            # 1. Fast idempotency check before mutating state
            existing = await self._find_trade_by_idem(session, user_id, idem_key)
            if existing is not None:
                return _to_trade_response(existing), False

            # 2. Validate referenced item & market exist
            item = await session.get(ItemORM, payload.item_id)
            if item is None:
                raise ResourceNotFoundError(f"Item #{payload.item_id} not found")
            market = await session.get(MarketORM, payload.market_id)
            if market is None:
                raise ResourceNotFoundError(f"Market #{payload.market_id} not found")

            # 3. Single atomic transaction with row-level lock on Position
            try:
                position = await self._lock_or_init_position(session, user_id, payload.item_id)

                # Re-check idempotency inside locked transaction for concurrent duplicate requests
                existing_locked = await self._find_trade_by_idem(session, user_id, idem_key)
                if existing_locked is not None:
                    await session.rollback()
                    return _to_trade_response(existing_locked), False

                traded_at = (
                    payload.traded_at
                    if payload.traded_at.tzinfo is not None
                    else payload.traded_at.replace(tzinfo=UTC)
                )

                new_trade = TradeORM(
                    user_id=user_id,
                    item_id=payload.item_id,
                    market_id=payload.market_id,
                    side=payload.side.value,
                    quantity=payload.qty,
                    price=payload.price.quantize(_Q4, rounding=ROUND_HALF_UP),
                    traded_at=traded_at,
                    idempotency_key=idem_key,
                )
                session.add(new_trade)
                await session.flush()

                # Replay ALL trades chronologically (handles backdated trades & sell validation)
                await self._recalculate_and_persist_position(
                    session,
                    user_id=user_id,
                    item_id=payload.item_id,
                    position=position,
                )

                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing_after = await self._find_trade_by_idem(session, user_id, idem_key)
                if existing_after is not None:
                    return _to_trade_response(existing_after), False
                raise
            except Exception:
                await session.rollback()
                raise

            loaded = await self._load_trade_with_relations(session, new_trade.id, user_id)
            logger.info(
                "trade_registered",
                trade_id=loaded.id,
                user_id=user_id,
                item_id=payload.item_id,
                side=payload.side.value,
                qty=payload.qty,
            )
            return _to_trade_response(loaded), True

    async def delete_trade(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        trade_id: int,
    ) -> None:
        """Delete user's own trade and recalculate position from start of history.

        Accessing another user's trade returns 404 (never 403) per specification.
        """
        trade = await session.scalar(
            select(TradeORM).where(TradeORM.id == trade_id, TradeORM.user_id == user_id)
        )
        if trade is None:
            raise ResourceNotFoundError(f"Trade #{trade_id} not found")

        item_id = trade.item_id
        lock = self._get_lock(user_id, item_id)
        async with lock:
            try:
                position = await self._lock_or_init_position(session, user_id, item_id)
                await session.delete(trade)
                await session.flush()

                await self._recalculate_and_persist_position(
                    session,
                    user_id=user_id,
                    item_id=item_id,
                    position=position,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        logger.info("trade_deleted", trade_id=trade_id, user_id=user_id, item_id=item_id)

    async def get_trade(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        trade_id: int,
    ) -> TradeResponse:
        """Return a trade owned by user_id, or 404 if missing or owned by someone else."""
        trade = await self._load_trade_with_relations(session, trade_id, user_id)
        return _to_trade_response(trade)

    async def list_trades(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        item_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[TradeResponse]:
        """List user's trade history filtered by optional item and time window."""
        stmt = (
            select(TradeORM)
            .options(selectinload(TradeORM.item), selectinload(TradeORM.market))
            .where(TradeORM.user_id == user_id)
            .order_by(TradeORM.traded_at.desc(), TradeORM.id.desc())
        )
        if item_id is not None:
            stmt = stmt.where(TradeORM.item_id == item_id)
        if date_from is not None:
            stmt = stmt.where(TradeORM.traded_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(TradeORM.traded_at <= date_to)

        rows = (await session.scalars(stmt)).all()
        return [_to_trade_response(r) for r in rows]

    async def get_position(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        position_id: int,
    ) -> PositionResponse:
        """Return a position owned by user_id, or 404 for missing/foreign positions."""
        stmt = (
            select(PositionORM)
            .options(selectinload(PositionORM.item).selectinload(ItemORM.game))
            .where(PositionORM.id == position_id, PositionORM.user_id == user_id)
        )
        pos = await session.scalar(stmt)
        if pos is None:
            raise ResourceNotFoundError(f"Position #{position_id} not found")
        return _to_position_response(pos)

    async def get_portfolio(
        self,
        session: AsyncSession,
        *,
        user_id: int,
    ) -> PortfolioSummaryResponse:
        """Return complete user portfolio summary including zero-quantity historical positions."""
        stmt = (
            select(PositionORM)
            .options(selectinload(PositionORM.item).selectinload(ItemORM.game))
            .where(PositionORM.user_id == user_id)
            .order_by(PositionORM.quantity.desc(), PositionORM.updated_at.desc())
        )
        rows = (await session.scalars(stmt)).all()
        positions = [_to_position_response(r) for r in rows]

        invested = sum((p.invested for p in positions), Decimal("0.00"))
        current_value = sum((p.current_value for p in positions), Decimal("0.00"))
        realized = sum((p.realized_pnl for p in positions), Decimal("0.00"))
        unrealized = sum((p.unrealized_pnl for p in positions), Decimal("0.00"))

        most_profitable = max(positions, key=lambda p: p.total_pnl) if positions else None
        least_profitable = min(positions, key=lambda p: p.total_pnl) if positions else None

        return PortfolioSummaryResponse(
            invested=invested.quantize(_Q2, rounding=ROUND_HALF_UP),
            current_value=current_value.quantize(_Q2, rounding=ROUND_HALF_UP),
            realized_pnl=realized.quantize(_Q2, rounding=ROUND_HALF_UP),
            unrealized_pnl=unrealized.quantize(_Q2, rounding=ROUND_HALF_UP),
            total_pnl=(realized + unrealized).quantize(_Q2, rounding=ROUND_HALF_UP),
            positions=positions,
            most_profitable=most_profitable,
            least_profitable=least_profitable,
        )

    async def _find_trade_by_idem(
        self,
        session: AsyncSession,
        user_id: int,
        idempotency_key: str,
    ) -> TradeORM | None:
        stmt = (
            select(TradeORM)
            .options(selectinload(TradeORM.item), selectinload(TradeORM.market))
            .where(TradeORM.user_id == user_id, TradeORM.idempotency_key == idempotency_key)
        )
        return await session.scalar(stmt)

    async def _load_trade_with_relations(
        self,
        session: AsyncSession,
        trade_id: int,
        user_id: int,
    ) -> TradeORM:
        stmt = (
            select(TradeORM)
            .options(selectinload(TradeORM.item), selectinload(TradeORM.market))
            .where(TradeORM.id == trade_id, TradeORM.user_id == user_id)
        )
        trade = await session.scalar(stmt)
        if trade is None:
            raise ResourceNotFoundError(f"Trade #{trade_id} not found")
        return trade

    async def _lock_or_init_position(
        self,
        session: AsyncSession,
        user_id: int,
        item_id: int,
    ) -> PositionORM:
        stmt = select(PositionORM).where(
            PositionORM.user_id == user_id,
            PositionORM.item_id == item_id,
        )
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update()

        position = await session.scalar(stmt)
        if position is None:
            position = PositionORM(
                user_id=user_id,
                item_id=item_id,
                quantity=0,
                avg_cost=Decimal("0.0000"),
                realized_pnl=Decimal("0.0000"),
            )
            session.add(position)
            await session.flush()
        return position

    async def _recalculate_and_persist_position(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        item_id: int,
        position: PositionORM,
    ) -> None:
        stmt = (
            select(TradeORM)
            .where(TradeORM.user_id == user_id, TradeORM.item_id == item_id)
            .order_by(TradeORM.traded_at.asc(), TradeORM.id.asc())
        )
        db_trades = (await session.scalars(stmt)).all()
        domain_trades = [
            TradeRecord(
                trade_id=t.id,
                side=TradeSide(t.side),
                quantity=t.quantity,
                price=Decimal(t.price),
                traded_at=_ensure_utc(t.traded_at),
            )
            for t in db_trades
        ]
        state = recalculate_position(domain_trades)
        position.quantity = state.quantity
        position.avg_cost = state.avg_cost
        position.realized_pnl = state.realized_pnl
        position.updated_at = datetime.now(UTC)


def _ensure_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_trade_response(trade: TradeORM) -> TradeResponse:
    return TradeResponse(
        id=trade.id,
        item_id=trade.item_id,
        item_name=trade.item.name if trade.item else "",
        market_id=trade.market_id,
        market_name=trade.market.name if trade.market else "",
        side=TradeSide(trade.side),
        quantity=trade.quantity,
        price=Decimal(trade.price),
        traded_at=trade.traded_at,
        idempotency_key=trade.idempotency_key,
        created_at=trade.created_at,
    )


def _to_position_response(pos: PositionORM) -> PositionResponse:
    current_price = (
        Decimal(pos.item.latest_min_price)
        if pos.item and pos.item.latest_min_price is not None
        else Decimal(pos.avg_cost)
    )
    invested = (Decimal(pos.avg_cost) * Decimal(pos.quantity)).quantize(
        _Q2, rounding=ROUND_HALF_UP
    )
    current_value = (current_price * Decimal(pos.quantity)).quantize(
        _Q2, rounding=ROUND_HALF_UP
    )
    realized = Decimal(pos.realized_pnl).quantize(_Q2, rounding=ROUND_HALF_UP)
    unrealized = (current_value - invested).quantize(_Q2, rounding=ROUND_HALF_UP)

    return PositionResponse(
        id=pos.id,
        item_id=pos.item_id,
        item_name=pos.item.name if pos.item else "",
        game_code=pos.item.game.code if pos.item and pos.item.game else "",
        quantity=pos.quantity,
        avg_cost=Decimal(pos.avg_cost),
        invested=invested,
        current_price=current_price,
        current_value=current_value,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        total_pnl=(realized + unrealized).quantize(_Q2, rounding=ROUND_HALF_UP),
        updated_at=pos.updated_at,
    )
