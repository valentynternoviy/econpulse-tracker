"""User watchlist and price threshold alert endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from econ_tracker.api.deps import AppContainer, get_container, get_current_user, get_session
from econ_tracker.api.errors import COMMON_ERROR_RESPONSES
from econ_tracker.services.schemas import (
    AlertResponse,
    WatchCreateRequest,
    WatchItemResponse,
    WatchUpdateRequest,
)
from econ_tracker.storage.orm_models import UserORM

router = APIRouter(prefix="/api/v1", tags=["Watchlist & Alerts"], responses=COMMON_ERROR_RESPONSES)


@router.get("/watch", response_model=list[WatchItemResponse])
async def list_watches(
    user: UserORM = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> list[WatchItemResponse]:
    return await container.watch_service.list_watches(session, user_id=user.id)


@router.post("/watch", response_model=WatchItemResponse, status_code=status.HTTP_201_CREATED)
async def create_watch(
    payload: WatchCreateRequest,
    response: Response,
    user: UserORM = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> WatchItemResponse:
    watch, created = await container.watch_service.create_or_get_watch(
        session,
        user_id=user.id,
        payload=payload,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return watch


@router.patch("/watch/{watch_id}", response_model=WatchItemResponse)
async def update_watch(
    watch_id: int,
    payload: WatchUpdateRequest,
    user: UserORM = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> WatchItemResponse:
    return await container.watch_service.update_watch(
        session,
        user_id=user.id,
        watch_id=watch_id,
        payload=payload,
    )


@router.delete("/watch/{watch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watch(
    watch_id: int,
    user: UserORM = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await container.watch_service.delete_watch(session, user_id=user.id, watch_id=watch_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/alerts", response_model=list[AlertResponse])
async def list_alerts(
    unread: bool = Query(default=False),
    user: UserORM = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> list[AlertResponse]:
    return await container.watch_service.list_alerts(
        session,
        user_id=user.id,
        unread_only=unread,
    )


@router.post("/alerts/{alert_id}/read", response_model=AlertResponse)
async def mark_alert_read(
    alert_id: int,
    user: UserORM = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> AlertResponse:
    return await container.watch_service.mark_alert_read(
        session,
        user_id=user.id,
        alert_id=alert_id,
    )
