"""Composition root.

All long-lived collaborators are constructed once here and stored on the
application. Nothing else in the codebase calls constructors of infrastructure
objects directly, which keeps wiring in one place and makes the app easy to
reconfigure for tests.
"""

from __future__ import annotations

import httpx
from redis.asyncio import Redis

from app.core.client_ip import ProxyTrust
from app.core.config import Settings
from app.core.rate_limit import InMemoryRateLimiter, RateLimiter, RedisRateLimiter
from app.db.session import create_engine, create_session_factory
from app.providers.currency import ExchangeRateProvider
from app.providers.http_client import ResilientHttpClient
from app.providers.sample_flights import SampleFlightProvider
from app.providers.sample_hotels import SampleHotelProvider
from app.providers.weather import OpenMeteoWeatherProvider
from app.resilience.cache import Cache, InMemoryCache, RedisCache
from app.resilience.circuit_breaker import CircuitBreaker
from app.services.aggregation import FlightAggregationService
from app.services.hotel_aggregation import HotelAggregationService
from app.services.notifications import ConsoleNotifier, Notifier
from app.services.token_blocklist import TokenBlocklist


class Container:
    def __init__(self, settings: Settings, *, cache: Cache | None = None) -> None:
        self.settings = settings
        self.engine = create_engine(settings)
        self.session_factory = create_session_factory(self.engine)
        # Prefer Redis (shared across nodes) when configured; otherwise stay
        # in-process, which is correct for a single node and for tests.
        self._redis: Redis | None = None
        if cache is not None:
            self.cache: Cache = cache
            self.rate_limiter: RateLimiter = InMemoryRateLimiter(
                limit=settings.rate_limit_per_minute
            )
        elif settings.redis_url is not None:
            self._redis = Redis.from_url(str(settings.redis_url))
            self.cache = RedisCache(self._redis)
            self.rate_limiter = RedisRateLimiter(self._redis, limit=settings.rate_limit_per_minute)
        else:
            self.cache = InMemoryCache()
            self.rate_limiter = InMemoryRateLimiter(limit=settings.rate_limit_per_minute)

        self.proxy_trust = ProxyTrust(settings.trusted_proxy_cidrs)
        self.token_blocklist = TokenBlocklist(self.cache)
        # Swap for SmtpNotifier in production (wired from settings).
        self.notifier: Notifier = ConsoleNotifier()

        self._http = httpx.AsyncClient(timeout=settings.http_timeout_seconds)

        self.weather_provider = OpenMeteoWeatherProvider(
            self._resilient("open-meteo"),
            base_url=settings.weather_base_url,
            cache_ttl=settings.provider_cache_ttl,
        )
        self.currency_provider = ExchangeRateProvider(
            self._resilient("exchangerate.host"),
            base_url=settings.currency_base_url,
            cache_ttl=settings.provider_cache_ttl,
        )
        self.flight_service = FlightAggregationService(
            [
                SampleFlightProvider("skyfare", ["Lufthansa", "KLM", "Emirates"]),
                SampleFlightProvider(
                    "globehop", ["Turkish Airlines", "Qatar Airways", "Emirates"], base_price=10500
                ),
            ]
        )
        self.hotel_service = HotelAggregationService(
            [
                SampleHotelProvider("stayfinder"),
                SampleHotelProvider("roomhub", base_price=6500),
            ]
        )

    def _resilient(self, provider: str) -> ResilientHttpClient:
        return ResilientHttpClient(
            self._http,
            provider=provider,
            cache=self.cache,
            max_retries=self.settings.http_max_retries,
            breaker=CircuitBreaker(provider),
        )

    async def aclose(self) -> None:
        await self._http.aclose()
        await self.engine.dispose()
        if self._redis is not None:
            await self._redis.aclose()
