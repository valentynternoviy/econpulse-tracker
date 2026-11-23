"""Unit tests for resilient HTTP client retries, FX fallback, and market adapters."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from econ_tracker.domain.exceptions import ExternalSourceError
from econ_tracker.sources.fx_rates import ExchangeRateProvider
from econ_tracker.sources.http_client import ResilientHttpClient
from econ_tracker.sources.rust_tm import RustTmSource
from econ_tracker.sources.skinport import SkinportRustSource
from econ_tracker.sources.warframe import WarframeMarketSource


@pytest.mark.unit
@respx.mock
async def test_http_client_retries_on_503_then_succeeds() -> None:
    route = respx.get("https://example.test/api").mock(
        side_effect=[
            httpx.Response(503, text="Service Unavailable"),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    client = ResilientHttpClient(
        timeout_seconds=5.0,
        max_retries=2,
        base_backoff_seconds=0.01,
        min_interval_seconds=0.0,
    )
    try:
        data = await client.get_json("https://example.test/api")
        assert data == {"ok": True}
        assert route.call_count == 2
    finally:
        await client.close()


@pytest.mark.unit
@respx.mock
async def test_http_client_wraps_network_error_preserving_cause() -> None:
    respx.get("https://down.test/api").mock(side_effect=httpx.ConnectTimeout("timed out"))
    client = ResilientHttpClient(
        timeout_seconds=1.0,
        max_retries=1,
        base_backoff_seconds=0.01,
        min_interval_seconds=0.0,
    )
    try:
        with pytest.raises(ExternalSourceError) as exc_info:
            await client.get_json("https://down.test/api")
        assert isinstance(exc_info.value.__cause__, httpx.ConnectTimeout)
    finally:
        await client.close()


@pytest.mark.unit
@respx.mock
async def test_fx_provider_falls_back_to_nbu_when_frankfurter_fails() -> None:
    respx.get("https://api.frankfurter.app/latest").mock(return_value=httpx.Response(503))
    respx.get("https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"cc": "USD", "rate": 40.0},
                {"cc": "EUR", "rate": 44.0},
            ],
        )
    )
    client = ResilientHttpClient(max_retries=0, min_interval_seconds=0.0)
    try:
        provider = ExchangeRateProvider(client, platinum_usd_rate=Decimal("0.05"))
        rates = await provider.get_rates_to_usd()
        assert rates["EUR"] == Decimal("1.100000")
        assert rates["PLT"] == Decimal("0.05")
    finally:
        await client.close()


@pytest.mark.unit
@respx.mock
async def test_market_adapters_yield_lazy_raw_quotes() -> None:
    respx.get("https://rust.tm/api/v2/prices/USD.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "items": [{"market_hash_name": "Alien Red", "price": "125.5", "volume": 9}],
            },
        )
    )
    respx.get("https://api.skinport.com/v1/items").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "market_hash_name": "Blackout Hoodie",
                    "min_price": 10.5,
                    "quantity": 12,
                    "created_at": 1700000000,
                }
            ],
        )
    )
    respx.get("https://api.warframe.market/v2/items").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "slug": "gauss_prime_set",
                        "tags": ["prime", "warframe", "set"],
                        "i18n": {"en": {"name": "Gauss Prime Set", "icon": "items/gauss.png"}},
                    }
                ]
            },
        )
    )
    respx.get("https://api.warframe.market/v2/orders/item/gauss_prime_set/top").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "sell": [{"platinum": 45, "quantity": 2}, {"platinum": 48, "quantity": 1}]
                }
            },
        )
    )

    client = ResilientHttpClient(max_retries=0, min_interval_seconds=0.0)
    try:
        rtm = list(await RustTmSource(client).fetch_quotes())
        assert len(rtm) == 1 and rtm[0].original_price == Decimal("125.5")

        sp = list(await SkinportRustSource(client).fetch_quotes())
        assert len(sp) == 1 and sp[0].subcategory == "hoodie" and sp[0].released_at is not None

        wf = list(await WarframeMarketSource(client, slugs=("gauss_prime_set",)).fetch_quotes())
        assert len(wf) == 1 and wf[0].original_price == Decimal("45") and wf[0].volume == 3
    finally:
        await client.close()
