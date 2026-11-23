"""Administrative management of games, markets, collection schedules, and run statuses."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from econ_tracker.domain.exceptions import ConflictError, ResourceNotFoundError
from econ_tracker.services.schemas import (
    GameCreateRequest,
    GameResponse,
    GameUpdateRequest,
    MarketCollectionStatusResponse,
    MarketCreateRequest,
    MarketResponse,
    MarketUpdateRequest,
)
from econ_tracker.storage.orm_models import CollectionRunORM, GameORM, MarketORM


class AdminService:
    """CRUD operations for games/markets and collector health overview."""

    async def create_game(
        self,
        session: AsyncSession,
        payload: GameCreateRequest,
    ) -> GameResponse:
        existing = await session.scalar(select(GameORM).where(GameORM.code == payload.code))
        if existing is not None:
            raise ConflictError(f"Game with code '{payload.code}' already exists")
        game = GameORM(name=payload.name, code=payload.code, is_active=payload.is_active)
        session.add(game)
        await session.commit()
        await session.refresh(game)
        return GameResponse(id=game.id, name=game.name, code=game.code, is_active=game.is_active)

    async def update_game(
        self,
        session: AsyncSession,
        game_id: int,
        payload: GameUpdateRequest,
    ) -> GameResponse:
        game = await session.get(GameORM, game_id)
        if game is None:
            raise ResourceNotFoundError(f"Game #{game_id} not found")
        if payload.name is not None:
            game.name = payload.name
        if payload.is_active is not None:
            game.is_active = payload.is_active
        await session.commit()
        await session.refresh(game)
        return GameResponse(id=game.id, name=game.name, code=game.code, is_active=game.is_active)

    async def list_markets(
        self,
        session: AsyncSession,
        *,
        game: str | None = None,
    ) -> list[MarketResponse]:
        stmt = (
            select(MarketORM)
            .join(GameORM, MarketORM.game_id == GameORM.id)
            .options(selectinload(MarketORM.game))
            .order_by(MarketORM.id.asc())
        )
        if game:
            stmt = stmt.where(GameORM.code == game.lower())
        rows = (await session.scalars(stmt)).all()
        return [_to_market_response(m) for m in rows]

    async def create_market(
        self,
        session: AsyncSession,
        payload: MarketCreateRequest,
    ) -> MarketResponse:
        game = await session.get(GameORM, payload.game_id)
        if game is None:
            raise ResourceNotFoundError(f"Game #{payload.game_id} not found")
        existing = await session.scalar(select(MarketORM).where(MarketORM.code == payload.code))
        if existing is not None:
            raise ConflictError(f"Market with code '{payload.code}' already exists")

        market = MarketORM(
            game_id=payload.game_id,
            name=payload.name,
            code=payload.code,
            base_url=payload.base_url,
            currency=payload.currency.upper(),
            fee_pct=payload.fee_pct,
            schedule_minutes=payload.schedule_minutes,
            is_active=payload.is_active,
        )
        session.add(market)
        await session.commit()
        loaded = await session.scalar(
            select(MarketORM).options(selectinload(MarketORM.game)).where(MarketORM.id == market.id)
        )
        assert loaded is not None
        return _to_market_response(loaded)

    async def update_market(
        self,
        session: AsyncSession,
        market_id: int,
        payload: MarketUpdateRequest,
    ) -> MarketResponse:
        market = await session.scalar(
            select(MarketORM).options(selectinload(MarketORM.game)).where(MarketORM.id == market_id)
        )
        if market is None:
            raise ResourceNotFoundError(f"Market #{market_id} not found")
        if payload.name is not None:
            market.name = payload.name
        if payload.fee_pct is not None:
            market.fee_pct = payload.fee_pct
        if payload.schedule_minutes is not None:
            market.schedule_minutes = payload.schedule_minutes
        if payload.is_active is not None:
            market.is_active = payload.is_active
        await session.commit()
        await session.refresh(market)
        return _to_market_response(market)

    async def get_collection_statuses(
        self,
        session: AsyncSession,
    ) -> list[MarketCollectionStatusResponse]:
        """Return latest collection metrics and error message for every market."""
        markets = (
            await session.scalars(
                select(MarketORM)
                .options(selectinload(MarketORM.game))
                .order_by(MarketORM.id.asc())
            )
        ).all()

        statuses: list[MarketCollectionStatusResponse] = []
        for m in markets:
            last_run = await session.scalar(
                select(CollectionRunORM)
                .where(CollectionRunORM.market_id == m.id)
                .order_by(CollectionRunORM.started_at.desc(), CollectionRunORM.id.desc())
                .limit(1)
            )
            statuses.append(
                MarketCollectionStatusResponse(
                    market_id=m.id,
                    market_code=m.code,
                    market_name=m.name,
                    game_code=m.game.code if m.game else "",
                    currency=m.currency,
                    schedule_minutes=m.schedule_minutes,
                    is_active=m.is_active,
                    last_run_at=last_run.started_at if last_run else m.last_collected_at,
                    last_status=last_run.status if last_run else None,
                    accepted_count=last_run.accepted_count if last_run else 0,
                    rejected_count=last_run.rejected_count if last_run else 0,
                    new_snapshots_count=last_run.new_snapshots_count if last_run else 0,
                    last_error=last_run.error_message if last_run else None,
                )
            )
        return statuses


def _to_market_response(m: MarketORM) -> MarketResponse:
    return MarketResponse(
        id=m.id,
        game_id=m.game_id,
        game_code=m.game.code if m.game else "",
        name=m.name,
        code=m.code,
        base_url=m.base_url,
        currency=m.currency,
        fee_pct=Decimal(m.fee_pct),
        schedule_minutes=m.schedule_minutes,
        is_active=m.is_active,
        last_collected_at=m.last_collected_at,
    )
