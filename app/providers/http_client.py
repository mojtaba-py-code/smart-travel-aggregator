"""Resilient HTTP client shared by every external provider adapter.

Wraps an ``httpx.AsyncClient`` with the patterns an aggregator cannot live
without: per-attempt timeouts, retry with exponential backoff on transient
failures, a circuit breaker per host, and optional response caching. The
underlying client is injected so tests can supply a mock transport.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

import httpx

from app.core.errors import ProviderUnavailableError
from app.core.logging import get_logger
from app.resilience.cache import Cache
from app.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

logger = get_logger("http_client")

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ResilientHttpClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        provider: str,
        cache: Cache | None = None,
        max_retries: int = 2,
        backoff_base: float = 0.2,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._client = client
        self._provider = provider
        self._cache = cache
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._breaker = breaker or CircuitBreaker(provider)

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        cache_ttl: int | None = None,
    ) -> Any:
        cache_key = self._cache_key(url, params) if cache_ttl and self._cache else None
        if cache_key is not None and self._cache is not None:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.debug("cache_hit", provider=self._provider, url=url)
                return json.loads(cached)

        try:
            payload = await self._breaker.call(lambda: self._get_with_retry(url, params))
        except CircuitBreakerOpen as exc:
            logger.warning("circuit_open", provider=self._provider)
            raise ProviderUnavailableError(f"{self._provider} is temporarily unavailable") from exc

        if cache_key is not None and self._cache is not None and cache_ttl:
            await self._cache.set(cache_key, json.dumps(payload), cache_ttl)
        return payload

    async def _get_with_retry(self, url: str, params: dict[str, Any] | None) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.get(url, params=params)
                if response.status_code in _RETRYABLE_STATUS:
                    raise httpx.HTTPStatusError(
                        f"retryable status {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    delay = self._backoff_base * (2**attempt)
                    logger.info(
                        "http_retry",
                        provider=self._provider,
                        attempt=attempt + 1,
                        delay=delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                break

        raise ProviderUnavailableError(
            f"{self._provider} request failed after {self._max_retries + 1} attempts"
        ) from last_exc

    def _cache_key(self, url: str, params: dict[str, Any] | None) -> str:
        raw = f"{self._provider}:{url}:{json.dumps(params or {}, sort_keys=True)}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:32]
        return f"http:{self._provider}:{digest}"
