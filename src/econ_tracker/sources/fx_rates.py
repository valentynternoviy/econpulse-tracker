"""Currency exchange rate provider (Frankfurter ECB primary, NBU fallback, PLT ref)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from econ_tracker.domain.exceptions import ExternalSourceError
from econ_tracker.logging_config import get_logger
from econ_tracker.sources.http_client import ResilientHttpClient

logger = get_logger(__name__)

_DEFAULT_FALLBACK_RATES: dict[str, Decimal] = {
    "USD": Decimal("1.000000"),
    "EUR": Decimal("1.080000"),
    "UAH": Decimal("0.024200"),
}

class ExchangeRateProvider:
    """Fetch live currency conversion rates into USD."""

    FRANKFURTER_URL = "https://api.frankfurter.app/latest"
    NBU_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json"

    def __init__(
        self,
        http_client: ResilientHttpClient,
        *,
        platinum_usd_rate: Decimal = Decimal("0.049990"),
    ) -> None:
        self._http = http_client
        self._platinum_usd_rate = platinum_usd_rate

    async def get_rates_to_usd(self) -> dict[str, Decimal]:
        """Return mapping {CURRENCY_CODE: rate_to_usd}."""
        rates: dict[str, Decimal] = {
            "USD": Decimal("1.000000"),
            "PLT": self._platinum_usd_rate,
        }

        try:
            payload: dict[str, Any] = await self._http.get_json(
                self.FRANKFURTER_URL,
                params={"from": "EUR", "to": "USD"},
            )
            eur_usd = payload.get("rates", {}).get("USD")
            if eur_usd is not None and Decimal(str(eur_usd)) > Decimal("0"):
                rates["EUR"] = Decimal(str(eur_usd)).quantize(Decimal("0.000001"))
                logger.info(
                    "fx_rates_fetched",
                    provider="frankfurter",
                    eur_to_usd=str(rates["EUR"]),
                )
                return rates
        except ExternalSourceError as exc:
            logger.warning("fx_primary_failed", provider="frankfurter", error=str(exc))

        try:
            nbu_rows: list[dict[str, Any]] = await self._http.get_json(self.NBU_URL)
            uah_per_usd: Decimal | None = None
            uah_per_eur: Decimal | None = None
            for row in nbu_rows:
                cc = str(row.get("cc", "")).upper()
                if cc == "USD":
                    uah_per_usd = Decimal(str(row["rate"]))
                elif cc == "EUR":
                    uah_per_eur = Decimal(str(row["rate"]))
            if uah_per_usd and uah_per_eur and uah_per_usd > Decimal("0"):
                rates["EUR"] = (uah_per_eur / uah_per_usd).quantize(Decimal("0.000001"))
                rates["UAH"] = (Decimal("1") / uah_per_usd).quantize(Decimal("0.000001"))
                logger.info("fx_rates_fetched", provider="nbu", eur_to_usd=str(rates["EUR"]))
                return rates
        except ExternalSourceError as exc:
            logger.warning("fx_secondary_failed", provider="nbu", error=str(exc))

        rates.setdefault("EUR", _DEFAULT_FALLBACK_RATES["EUR"])
        logger.warning("fx_using_fallback_rates", eur_to_usd=str(rates["EUR"]))
        return rates
