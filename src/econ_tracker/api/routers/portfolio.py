"""Portfolio and Trade routes (KEY STATE-CHANGING OPERATION)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from econ_tracker.api.deps import AppContainer, get_container, get_current_user, get_session
from econ_tracker.api.errors import COMMON_ERROR_RESPONSES
from econ_tracker.services.schemas import (
    PortfolioSummaryResponse,
    PositionResponse,
    TradeCreateRequest,
    TradeResponse,
)
from econ_tracker.storage.orm_models import UserORM

router = APIRouter(prefix="/api/v1", tags=["Portfolio & Trades"], responses=COMMON_ERROR_RESPONSES)


@router.post("/trades", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
async def create_trade(
    payload: TradeCreateRequest,
    response: Response,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    user: UserORM = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> TradeResponse:
    if payload.idempotency_key is None and idempotency_key_header:
        payload = payload.model_copy(update={"idempotency_key": idempotency_key_header.strip()})

    trade, created = await container.portfolio_service.create_trade(
        session,
        user_id=user.id,
        payload=payload,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return trade


@router.get("/trades", response_model=list[TradeResponse])
async def list_trades(
    item_id: int | None = Query(default=None, gt=0),
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    user: UserORM = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> list[TradeResponse]:
    return await container.portfolio_service.list_trades(
        session,
        user_id=user.id,
        item_id=item_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/trades/{trade_id}", response_model=TradeResponse)
async def get_trade(
    trade_id: int,
    user: UserORM = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> TradeResponse:
    return await container.portfolio_service.get_trade(
        session,
        user_id=user.id,
        trade_id=trade_id,
    )


@router.delete("/trades/{trade_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trade(
    trade_id: int,
    user: UserORM = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await container.portfolio_service.delete_trade(
        session,
        user_id=user.id,
        trade_id=trade_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/portfolio", response_model=PortfolioSummaryResponse)
async def get_portfolio(
    user: UserORM = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> PortfolioSummaryResponse:
    return await container.portfolio_service.get_portfolio(session, user_id=user.id)


@router.get("/portfolio/positions/{position_id}", response_model=PositionResponse)
async def get_position(
    position_id: int,
    user: UserORM = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> PositionResponse:
    return await container.portfolio_service.get_position(
        session,
        user_id=user.id,
        position_id=position_id,
    )
