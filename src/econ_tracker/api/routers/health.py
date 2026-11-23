"""Service health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from econ_tracker import __version__
from econ_tracker.api.deps import AppContainer, get_container
from econ_tracker.storage.database import check_database_health

router = APIRouter(tags=["Health"])


@router.get("/healthz", summary="Check service and database liveness")
async def healthz(
    response: Response,
    container: AppContainer = Depends(get_container),
) -> dict[str, str]:
    db_ok = await check_database_health(container.engine)
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "database": "unreachable", "version": __version__}
    return {"status": "ok", "database": "connected", "version": __version__}
