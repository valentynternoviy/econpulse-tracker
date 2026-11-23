"""Shared pytest fixtures for integration and E2E tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from econ_tracker.api.app import create_app
from econ_tracker.api.deps import AppContainer
from econ_tracker.config import Settings
from econ_tracker.domain.exceptions import ExternalSourceError
from econ_tracker.domain.models import RawMarketQuote
from econ_tracker.storage.database import Base
from econ_tracker.storage.seed import seed_database


class FakeFxProvider:
    async def get_rates_to_usd(self) -> dict[str, Decimal]:
        return {
            "USD": Decimal("1.000000"),
            "EUR": Decimal("1.100000"),
            "PLT": Decimal("0.050000"),
        }

class StaticMarketAdapter:
    def __init__(
        self,
        *,
        market_code: str,
        game_code: str,
        currency: str,
        quotes: list[RawMarketQuote] | None = None,
        fail_with: str | None = None,
    ) -> None:
        self.market_code = market_code
        self.game_code = game_code
        self.currency = currency
        self._quotes = quotes or []
        self._fail_with = fail_with

    async def fetch_quotes(self) -> Iterator[RawMarketQuote]:
        if self._fail_with is not None:
            raise ExternalSourceError(self._fail_with)
        return iter(self._quotes)

@pytest.fixture
async def seeded_app(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, AppContainer]]:
    """Build an isolated FastAPI app backed by a fresh seeded SQLite test DB."""
    db_path = tmp_path / "test_econ.db"
    settings = Settings(
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        collect_enabled=False,
        log_json=False,
    )
    now = datetime.now(UTC)
    adapters = {
        "wf_pc": StaticMarketAdapter(
            market_code="wf_pc",
            game_code="warframe",
            currency="PLT",
            quotes=[
                RawMarketQuote(
                    external_id="gauss_prime_set",
                    name="Gauss Prime Set",
                    original_price=Decimal("40"),
                    original_currency="PLT",
                    volume=52,
                    collected_at=now,
                    item_type="warframes",
                    subcategory="prime_set",
                    rarity="prime",
                ),
                RawMarketQuote(
                    external_id="broken_item",
                    name="Broken Zero Price",
                    original_price=Decimal("-5"),
                    original_currency="PLT",
                    volume=10,
                    collected_at=now,
                ),
            ],
        ),
        "wf_ps": StaticMarketAdapter(
            market_code="wf_ps",
            game_code="warframe",
            currency="PLT",
            fail_with="Simulated PS market upstream outage",
        ),
        "skinport_rust": StaticMarketAdapter(
            market_code="skinport_rust",
            game_code="rust",
            currency="EUR",
            quotes=[
                RawMarketQuote(
                    external_id="Alien Red",
                    name="Alien Red",
                    original_price=Decimal("100.00"),
                    original_currency="EUR",
                    volume=18,
                    collected_at=now,
                    item_type="weapons",
                    subcategory="ak47",
                    rarity="legendary",
                )
            ],
        ),
        "rust_tm": StaticMarketAdapter(
            market_code="rust_tm",
            game_code="rust",
            currency="USD",
            quotes=[
                RawMarketQuote(
                    external_id="Alien Red",
                    name="Alien Red",
                    original_price=Decimal("120.00"),
                    original_currency="USD",
                    volume=22,
                    collected_at=now,
                    item_type="weapons",
                    subcategory="ak47",
                    rarity="legendary",
                )
            ],
        ),
    }

    container = AppContainer.build(
        settings,
        adapters=adapters,  # type: ignore[arg-type]
        fx_provider=FakeFxProvider(),
    )
    async with container.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with container.session_factory() as session:
        await seed_database(session, days=10, max_items_per_game=160)

    app = create_app(settings=settings, container=container)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, container

    await container.shutdown()

async def auth_headers(client: httpx.AsyncClient, username: str, password: str) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
