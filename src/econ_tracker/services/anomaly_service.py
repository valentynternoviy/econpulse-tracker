"""Price anomaly event query and analyst confirmation/closure service."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from econ_tracker.domain.enums import AnomalyStatus
from econ_tracker.domain.exceptions import ConflictError, ResourceNotFoundError
from econ_tracker.services.schemas import AnomalyResponse
from econ_tracker.storage.orm_models import AnomalyEventORM, GameORM, ItemORM


class AnomalyService:
    """List open/closed anomaly events and allow analysts to close them with comments."""

    async def list_anomalies(
        self,
        session: AsyncSession,
        *,
        status: AnomalyStatus | None = None,
        game: str | None = None,
    ) -> list[AnomalyResponse]:
        stmt = (
            select(AnomalyEventORM)
            .join(ItemORM, AnomalyEventORM.item_id == ItemORM.id)
            .join(GameORM, ItemORM.game_id == GameORM.id)
            .options(
                selectinload(AnomalyEventORM.item).selectinload(ItemORM.game),
                selectinload(AnomalyEventORM.market),
            )
            .order_by(AnomalyEventORM.opened_at.desc())
            .limit(200)
        )
        if status is not None:
            stmt = stmt.where(AnomalyEventORM.status == status.value)
        if game:
            stmt = stmt.where(GameORM.code == game.lower())

        rows = (await session.scalars(stmt)).all()
        return [_to_anomaly_response(r) for r in rows]

    async def close_anomaly(
        self,
        session: AsyncSession,
        *,
        anomaly_id: int,
        analyst_user_id: int,
        comment: str,
    ) -> AnomalyResponse:
        stmt = (
            select(AnomalyEventORM)
            .options(
                selectinload(AnomalyEventORM.item).selectinload(ItemORM.game),
                selectinload(AnomalyEventORM.market),
            )
            .where(AnomalyEventORM.id == anomaly_id)
        )
        event = await session.scalar(stmt)
        if event is None:
            raise ResourceNotFoundError(f"Anomaly event #{anomaly_id} not found")
        if event.status == AnomalyStatus.CLOSED.value:
            raise ConflictError(f"Anomaly event #{anomaly_id} is already closed")

        event.status = AnomalyStatus.CLOSED.value
        event.closed_at = datetime.now(UTC)
        event.closed_by_user_id = analyst_user_id
        event.comment = comment.strip()
        await session.commit()
        await session.refresh(event)
        return _to_anomaly_response(event)


def _to_anomaly_response(e: AnomalyEventORM) -> AnomalyResponse:
    opened = e.opened_at if e.opened_at.tzinfo is not None else e.opened_at.replace(tzinfo=UTC)
    end_dt = (
        (e.closed_at if e.closed_at.tzinfo is not None else e.closed_at.replace(tzinfo=UTC))
        if e.closed_at is not None
        else datetime.now(UTC)
    )
    duration_min = max(0, int((end_dt - opened).total_seconds() // 60))

    return AnomalyResponse(
        id=e.id,
        item_id=e.item_id,
        item_name=e.item.name if e.item else "",
        game_code=e.item.game.code if e.item and e.item.game else "",
        market_id=e.market_id,
        market_name=e.market.name if e.market else "",
        status=AnomalyStatus(e.status),
        ma7_price=Decimal(e.ma7_price),
        trigger_price=Decimal(e.trigger_price),
        deviation_pct=Decimal(e.deviation_pct),
        max_deviation_pct=Decimal(e.max_deviation_pct),
        opened_at=opened,
        closed_at=e.closed_at,
        duration_minutes=duration_min,
        comment=e.comment,
    )
