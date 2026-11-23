"""FastAPI application factory with lifespan scheduler, RFC 9457 errors, and web UI mounting."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from econ_tracker import __version__
from econ_tracker.api.deps import AppContainer
from econ_tracker.api.errors import register_exception_handlers
from econ_tracker.api.middleware import CorrelationIdMiddleware
from econ_tracker.api.routers import (
    admin,
    anomalies,
    auth,
    health,
    items,
    portfolio,
    stats,
    watch,
)
from econ_tracker.config import Settings, get_settings
from econ_tracker.logging_config import configure_logging, get_logger

logger = get_logger(__name__)

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
_STATIC_DIR = _WEB_DIR / "static"


async def _scheduler_loop(container: AppContainer, interval_minutes: int = 15) -> None:
    """Periodic collection loop enforcing minimum 15-minute interval per market."""
    wait_seconds = max(15, interval_minutes) * 60
    while True:
        await asyncio.sleep(wait_seconds)
        try:
            logger.info("scheduled_collection_started")
            await container.collector_service.run_collection()
        except Exception:
            logger.exception("scheduled_collection_failed")


def create_app(
    *,
    settings: Settings | None = None,
    container: AppContainer | None = None,
) -> FastAPI:
    """Build and wire the FastAPI ASGI application."""
    cfg = settings or get_settings()
    configure_logging(level=cfg.log_level, json_logs=cfg.log_json)

    app_container = container or AppContainer.build(cfg)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = app_container
        scheduler_task: asyncio.Task[None] | None = None
        if cfg.collect_enabled and cfg.app_env != "test":
            scheduler_task = asyncio.create_task(_scheduler_loop(app_container, 15))
        logger.info("application_started", env=cfg.app_env, version=__version__)
        try:
            yield
        finally:
            if scheduler_task is not None:
                scheduler_task.cancel()
                with suppress(asyncio.CancelledError):
                    await scheduler_task
            await app_container.shutdown()
            logger.info("application_stopped")

    app = FastAPI(
        title="EconPulse — Game Economy & Virtual Markets API",
        version=__version__,
        description=(
            "REST API for monitoring Warframe & Rust virtual item economies: "
            "multi-market price collection, currency normalization, aggregated history, "
            "watchlist alerts, 7-day moving average anomaly detection, and transactional portfolio."
        ),
        lifespan=lifespan,
    )
    app.state.container = app_container

    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)

    for router in (
        health.router,
        auth.router,
        items.router,
        watch.router,
        portfolio.router,
        anomalies.router,
        stats.router,
        admin.router,
    ):
        app.include_router(router)

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False, response_model=None)
    async def web_root() -> FileResponse | HTMLResponse:
        index_file = _WEB_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return HTMLResponse(
            "<h1>EconPulse API</h1><p>OpenAPI docs available at <a href='/docs'>/docs</a>.</p>"
        )

    return app
