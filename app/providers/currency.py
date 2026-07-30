"""exchangerate.host currency adapter (free tier)."""

from __future__ import annotations

from typing import Any

from app.core.errors import ProviderUnavailableError
from app.domain.dto import CurrencyConversion
from app.providers.http_client import ResilientHttpClient


class ExchangeRateProvider:
    name = "exchangerate.host"

    def __init__(self, http: ResilientHttpClient, *, base_url: str, cache_ttl: int) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._cache_ttl = cache_ttl

    async def convert(self, base: str, quote: str, amount: float) -> CurrencyConversion:
        params = {"from": base.upper(), "to": quote.upper(), "amount": amount}
        payload = await self._http.get_json(
            f"{self._base_url}/convert", params=params, cache_ttl=self._cache_ttl
        )
        return self._normalize(payload, base, quote, amount)

    def _normalize(
        self, payload: Any, base: str, quote: str, amount: float
    ) -> CurrencyConversion:
        try:
            info = payload["info"]
            rate = float(info["rate"])
            converted = float(payload["result"])
            as_of = str(payload.get("date", ""))
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderUnavailableError(
                "exchangerate.host returned an unexpected payload"
            ) from exc

        return CurrencyConversion(
            base=base.upper(),
            quote=quote.upper(),
            rate=rate,
            amount=amount,
            converted=round(converted, 4),
            as_of=as_of,
        )
