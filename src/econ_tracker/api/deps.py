"""Composition root container and FastAPI dependency providers."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from decimal import Decimal

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from econ_tracker.config import Settings
from econ_tracker.domain.enums import UserRole
from econ_tracker.domain.exceptions import AuthenticationError, AuthorizationError
from econ_tracker.services.admin_service import AdminService
from econ_tracker.services.analytics_service import AnalyticsService
from econ_tracker.services.anomaly_service import AnomalyService
from econ_tracker.services.auth_service import AuthService
from econ_tracker.services.catalog_service import CatalogService
from econ_tracker.services.collector_service import CollectorService
from econ_tracker.services.portfolio_service import PortfolioService
from econ_tracker.services.protocols import FxProviderProtocol, MarketSourceProtocol
from econ_tracker.services.watch_service import WatchService
from econ_tracker.sources.fx_rates import ExchangeRateProvider
from econ_tracker.sources.http_client import ResilientHttpClient
from econ_tracker.sources.registry import build_default_adapters
from econ_tracker.storage.database import create_engine_and_sessionmaker
from econ_tracker.storage.orm_models import UserORM

_bearer = HTTPBearer(auto_error=False)


@dataclass
class AppContainer:
    """Single composition root holding wired services and infrastructure handles."""

    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    http_client: ResilientHttpClient
    auth_service: AuthService
    catalog_service: CatalogService
    portfolio_service: PortfolioService
    watch_service: WatchService
    anomaly_service: AnomalyService
    analytics_service: AnalyticsService
    admin_service: AdminService
    collector_service: CollectorService

    @classmethod
    def build(
        cls,
        settings: Settings,
        *,
        adapters: dict[str, MarketSourceProtocol] | None = None,
        fx_provider: FxProviderProtocol | None = None,
    ) -> AppContainer:
        engine, session_factory = create_engine_and_sessionmaker(
            settings.database_url,
            echo=settings.debug,
        )
        http_client = ResilientHttpClient(
            timeout_seconds=settings.collect_timeout_seconds,
            max_retries=settings.collect_max_retries,
        )
        resolved_adapters: dict[str, MarketSourceProtocol] = (
            adapters if adapters is not None else dict(build_default_adapters(http_client))
        )
        resolved_fx: FxProviderProtocol = (
            fx_provider
            if fx_provider is not None
            else ExchangeRateProvider(
                http_client,
                platinum_usd_rate=Decimal(str(settings.platinum_usd_rate)),
            )
        )
        return cls(
            settings=settings,
            engine=engine,
            session_factory=session_factory,
            http_client=http_client,
            auth_service=AuthService(settings),
            catalog_service=CatalogService(),
            portfolio_service=PortfolioService(),
            watch_service=WatchService(),
            anomaly_service=AnomalyService(),
            analytics_service=AnalyticsService(),
            admin_service=AdminService(),
            collector_service=CollectorService(
                session_factory=session_factory,
                adapters=resolved_adapters,
                fx_provider=resolved_fx,
                concurrency=settings.collect_concurrency,
                anomaly_threshold_pct=Decimal(str(settings.anomaly_threshold_pct)),
            ),
        )

    async def shutdown(self) -> None:
        await self.http_client.close()
        await self.engine.dispose()


def get_container(request: Request) -> AppContainer:
    container: AppContainer = request.app.state.container
    return container


async def get_session(
    container: AppContainer = Depends(get_container),
) -> AsyncIterator[AsyncSession]:
    async with container.session_factory() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> UserORM:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer access token")
    payload = container.auth_service.decode_token(credentials.credentials)
    sub = payload.get("sub")
    if sub is None:
        raise AuthenticationError("Token missing subject claim")
    return await container.auth_service.get_user_by_id(session, int(sub))


def require_roles(*allowed: UserRole) -> Callable[..., UserORM]:
    """Dependency enforcing that the authenticated user holds one of the allowed roles."""
    allowed_values = {r.value for r in allowed}

    def _checker(user: UserORM = Depends(get_current_user)) -> UserORM:
        if user.role not in allowed_values:
            raise AuthorizationError(
                f"Role '{user.role}' is not permitted for this operation"
            )
        return user

    return _checker
