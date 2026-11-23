"""Price anomaly event listing and analyst close endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from econ_tracker.api.deps import AppContainer, get_container, get_session, require_roles
from econ_tracker.api.errors import COMMON_ERROR_RESPONSES
from econ_tracker.domain.enums import AnomalyStatus, UserRole
from econ_tracker.services.schemas import AnomalyCloseRequest, AnomalyResponse
from econ_tracker.storage.orm_models import UserORM

router = APIRouter(prefix="/api/v1", tags=["Anomalies"], responses=COMMON_ERROR_RESPONSES)


@router.get("/anomalies", response_model=list[AnomalyResponse])
async def list_anomalies(
    status_filter: AnomalyStatus | None = Query(default=None, alias="status"),
    game: str | None = Query(default=None, max_length=32),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> list[AnomalyResponse]:
    return await container.anomaly_service.list_anomalies(
        session,
        status=status_filter,
        game=game,
    )


@router.post("/anomalies/{anomaly_id}/close", response_model=AnomalyResponse)
async def close_anomaly(
    anomaly_id: int,
    payload: AnomalyCloseRequest,
    analyst: UserORM = Depends(require_roles(UserRole.ANALYST, UserRole.ADMIN)),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> AnomalyResponse:
    return await container.anomaly_service.close_anomaly(
        session,
        anomaly_id=anomaly_id,
        analyst_user_id=analyst.id,
        comment=payload.comment,
    )
