# Architecture

## Layered / clean architecture

```
┌─────────────────────────────────────────────────────────┐
│ Presentation      app/api/v1  — routers, DTO wiring       │
├─────────────────────────────────────────────────────────┤
│ Business logic    app/services — aggregation, auth, ...   │
├─────────────────────────────────────────────────────────┤
│ Domain            app/domain — entities, ports, Money     │
├─────────────────────────────────────────────────────────┤
│ Adapters          app/providers — external API clients    │
├─────────────────────────────────────────────────────────┤
│ Repositories      app/repositories — SQLAlchemy access    │
├─────────────────────────────────────────────────────────┤
│ Infrastructure    app/db, app/resilience, app/workers     │
└─────────────────────────────────────────────────────────┘
    Cross-cutting: config · security · logging · rate limit · DI
```

Outer layers depend on inner layers only through interfaces (`app/domain/ports.py`).
The composition root (`app/container.py`) is the one place that constructs
concrete infrastructure and injects it, so nothing else is coupled to a vendor
SDK or a specific database.

## Flight search request flow

```
Client
  │  GET /api/v1/flights/search?...
  ▼
API router  ── validates query params (IATA codes, dates, ranges)
  │            enforces rate limit, resolves optional user
  ▼
FlightAggregationService
  │  asyncio.gather over providers  ← concurrent fan-out
  ├─ provider A (circuit breaker + retry + cache)
  ├─ provider B (circuit breaker + retry + cache)
  │  a failed provider is dropped, response flagged `degraded`
  ▼
dedupe (cheapest wins) → rank (price/duration/stops) → sort → paginate (cursor)
  │
  ▼
FlightSearchResponse (RFC-friendly envelope, problem+json on error)
```

## Error handling

All errors are rendered as RFC 7807 `application/problem+json`:

- `AppError` subclasses → mapped status + stable `code`
- `RequestValidationError` → `422` with a cleaned `errors` list
- Unhandled exceptions → `500` generic message, real error logged server-side

Every response body carries the request's `trace_id`, and every response header
carries `X-Request-ID` for correlation with the structured logs.

## Data model

- **User** 1─N **SearchHistory**, 1─N **PriceAlert**
- **AuditLog** — append-only record of security events (register, login)
- Flight/hotel offers are normalized DTOs carrying the raw provider payload for
  auditability; money is always `{amount_minor, currency}`.

## Resilience patterns

| Pattern | Where |
| ------- | ----- |
| Circuit breaker (per provider) | `app/resilience/circuit_breaker.py` |
| Retry + exponential backoff | `app/providers/http_client.py` |
| Timeout | injected `httpx.AsyncClient` |
| Cache (memory/Redis) | `app/resilience/cache.py` |
| Graceful degradation | `app/services/aggregation.py` |
| Rate limiting | `app/core/rate_limit.py` |
