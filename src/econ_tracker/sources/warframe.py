"""Warframe Market API v2 adapter (Platinum player orders for PC and Console platforms)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from econ_tracker.domain.exceptions import ExternalSourceError
from econ_tracker.domain.logic import classify_warframe_item
from econ_tracker.domain.models import RawMarketQuote
from econ_tracker.logging_config import get_logger
from econ_tracker.sources.http_client import ResilientHttpClient

logger = get_logger(__name__)

_ASSET_BASE = "https://warframe.market/static/assets/"

DEFAULT_WARFRAME_SLUGS: tuple[str, ...] = (
    "gauss_prime_set",
    "wisp_prime_set",
    "revenant_prime_set",
    "saryn_prime_set",
    "mesa_prime_set",
    "volt_prime_set",
    "glaive_prime_set",
    "nikana_prime_set",
    "torid_set",
    "arcane_energize",
    "arcane_grace",
    "arcane_avenger",
    "arcane_barrier",
    "primed_continuity",
    "primed_flow",
    "primed_sure_footed",
    "primed_pressure_point",
    "condition_overload",
    "adaptation",
    "rolling_guard",
)

class WarframeMarketSource:
    """Fetch live Warframe player sell orders in Platinum via api.warframe.market/v2."""

    game_code = "warframe"
    currency = "PLT"
    base_url = "https://api.warframe.market/v2"

    def __init__(
        self,
        http_client: ResilientHttpClient,
        *,
        platform: str = "pc",
        market_code: str | None = None,
        slugs: tuple[str, ...] = DEFAULT_WARFRAME_SLUGS,
    ) -> None:
        self._http = http_client
        self._platform = platform
        self.market_code = market_code or f"wf_{platform}"
        self._slugs = slugs

    async def fetch_quotes(self) -> Iterator[RawMarketQuote]:
        """Fetch catalog metadata and top online sell orders for tracked Warframe items."""
        headers = {"Platform": self._platform, "Language": "en"}
        catalog_resp: Any = await self._http.get_json(f"{self.base_url}/items", headers=headers)
        if not isinstance(catalog_resp, dict) or not isinstance(catalog_resp.get("data"), list):
            raise ExternalSourceError("Unexpected catalog response from warframe.market v2")

        by_slug: dict[str, dict[str, Any]] = {
            str(entry["slug"]): entry
            for entry in catalog_resp["data"]
            if isinstance(entry, dict) and entry.get("slug")
        }

        collected_at = datetime.now(UTC)
        quotes: list[RawMarketQuote] = []

        for slug in self._slugs:
            meta = by_slug.get(slug)
            if meta is None:
                continue
            try:
                orders_resp: Any = await self._http.get_json(
                    f"{self.base_url}/orders/item/{slug}/top",
                    headers=headers,
                )
            except ExternalSourceError as exc:
                logger.warning(
                    "warframe_order_fetch_skipped",
                    slug=slug,
                    platform=self._platform,
                    error=str(exc),
                )
                continue

            sell_orders = (
                orders_resp.get("data", {}).get("sell", [])
                if isinstance(orders_resp, dict)
                else []
            )
            if not sell_orders:
                continue

            prices = [
                Decimal(str(o["platinum"]))
                for o in sell_orders
                if isinstance(o, dict) and o.get("platinum") is not None
            ]
            if not prices:
                continue

            min_price = min(prices)
            total_qty = sum(
                max(1, int(o.get("quantity", 1)))
                for o in sell_orders
                if isinstance(o, dict)
            )

            raw_i18n = meta.get("i18n")
            i18n_en = raw_i18n.get("en", {}) if isinstance(raw_i18n, dict) else {}
            name = str(i18n_en.get("name") or slug.replace("_", " ").title())
            icon_rel = i18n_en.get("icon") or i18n_en.get("thumb")
            icon_url = f"{_ASSET_BASE}{icon_rel}" if icon_rel else None
            tags = tuple(str(t) for t in meta.get("tags", []) if isinstance(t, str))
            category, subcategory, rarity = classify_warframe_item(tags, name)

            quotes.append(
                RawMarketQuote(
                    external_id=slug,
                    name=name,
                    original_price=min_price,
                    original_currency=self.currency,
                    volume=total_qty,
                    collected_at=collected_at,
                    item_type=category,
                    subcategory=subcategory,
                    rarity=rarity,
                    icon_url=icon_url,
                    extra_tags=tags,
                )
            )

        return iter(quotes)
