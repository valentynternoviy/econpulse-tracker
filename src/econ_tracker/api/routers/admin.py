"""Administration routes: manage games, markets, collection schedule, manual collection runs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from econ_tracker.api.deps import AppContainer, get_container, get_session, require_roles
from econ_tracker.api.errors import COMMON_ERROR_RESPONSES
from econ_tracker.domain.enums import UserRole
from econ_tracker.services.schemas import (
    CollectionRunResponse,
    CollectRunRequest,
    GameCreateRequest,
    GameResponse,
    GameUpdateRequest,
    MarketCollectionStatusResponse,
    MarketCreateRequest,
    MarketResponse,
    MarketUpdateRequest,
)
from econ_tracker.storage.orm_models import UserORM

router = APIRouter(prefix="/api/v1", tags=["Administration"], responses=COMMON_ERROR_RESPONSES)


@router.post("/admin/games", response_model=GameResponse, status_code=status.HTTP_201_CREATED)
async def create_game(
    payload: GameCreateRequest,
    _admin: UserORM = Depends(require_roles(UserRole.ADMIN)),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> GameResponse:
    return await container.admin_service.create_game(session, payload)


@router.patch("/admin/games/{game_id}", response_model=GameResponse)
async def update_game(
    game_id: int,
    payload: GameUpdateRequest,
    _admin: UserORM = Depends(require_roles(UserRole.ADMIN)),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> GameResponse:
    return await container.admin_service.update_game(session, game_id, payload)


@router.post("/admin/markets", response_model=MarketResponse, status_code=status.HTTP_201_CREATED)
async def create_market(
    payload: MarketCreateRequest,
    _admin: UserORM = Depends(require_roles(UserRole.ADMIN)),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> MarketResponse:
    return await container.admin_service.create_market(session, payload)


@router.patch("/admin/markets/{market_id}", response_model=MarketResponse)
async def update_market(
    market_id: int,
    payload: MarketUpdateRequest,
    _admin: UserORM = Depends(require_roles(UserRole.ADMIN)),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> MarketResponse:
    return await container.admin_service.update_market(session, market_id, payload)


@router.get("/admin/collection/status", response_model=list[MarketCollectionStatusResponse])
async def collection_status(
    _staff: UserORM = Depends(require_roles(UserRole.ADMIN, UserRole.ANALYST)),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> list[MarketCollectionStatusResponse]:
    return await container.admin_service.get_collection_statuses(session)


@router.post("/collect/run", response_model=list[CollectionRunResponse])
async def run_collection(
    payload: CollectRunRequest | None = None,
    _admin: UserORM = Depends(require_roles(UserRole.ADMIN)),
    container: AppContainer = Depends(get_container),
) -> list[CollectionRunResponse]:
    market_id = payload.market_id if payload is not None else None
    return await container.collector_service.run_collection(market_id=market_id)
