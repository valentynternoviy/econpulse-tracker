"""Factory registry mapping market codes to concrete async source adapters."""

from __future__ import annotations

from econ_tracker.sources.http_client import ResilientHttpClient
from econ_tracker.sources.rust_tm import RustTmSource
from econ_tracker.sources.skinport import SkinportRustSource
from econ_tracker.sources.warframe import WarframeMarketSource

MarketAdapter = RustTmSource | SkinportRustSource | WarframeMarketSource


def build_default_adapters(http_client: ResilientHttpClient) -> dict[str, MarketAdapter]:
    """Instantiate all configured marketplace adapters."""
    adapters: list[MarketAdapter] = [
        WarframeMarketSource(http_client, platform="pc", market_code="wf_pc"),
        WarframeMarketSource(http_client, platform="ps4", market_code="wf_ps"),
        SkinportRustSource(http_client, max_items=350),
        RustTmSource(http_client, max_items=350),
    ]
    return {adapter.market_code: adapter for adapter in adapters}
