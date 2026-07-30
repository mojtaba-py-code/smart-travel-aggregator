# Smart Travel Aggregator

[![CI](https://github.com/mojtaba-py-code/smart-travel-aggregator/actions/workflows/ci.yml/badge.svg)](https://github.com/mojtaba-py-code/smart-travel-aggregator/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org)
[![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen.svg)](#testing--quality)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A production-minded travel aggregation platform. It fans out to multiple travel
providers (flights, hotels, weather, currency), normalizes their responses,
ranks them, and serves the result through one clean, versioned, resilient REST
API — with authentication, rate limiting, structured logging and a strong test
suite baked in from the start.

> Built with FastAPI + async SQLAlchemy 2.x, following a clean, layered
> architecture with dependency injection. The design goal is a codebase that
> could be handed to a team and deployed for real users, not a tutorial.

---

## Highlights

- **Aggregation core** — provider adapters behind stable ports; concurrent
  fan-out, de-duplication, ranking, and **graceful degradation** (a failing
  provider is dropped and the response is flagged `degraded`, never a 500).
- **Security first** — Argon2id password hashing, JWT access/refresh tokens with
  a `type` claim, email verification, password reset, logout via token
  revocation (denylist), RBAC, per-client rate limiting, hardened HTTP headers,
  and an append-only audit log.
- **Input validation everywhere** — Pydantic v2 models and typed query
  parameters reject bad input at the edge; errors come back as RFC 7807
  `application/problem+json` with a `trace_id`.
- **Resilience** — per-provider circuit breaker, retry with exponential backoff,
  timeouts, and a pluggable cache (in-memory for dev/tests, Redis for prod).
- **Observability** — structured JSON logs (structlog) with a request-id stamped
  on every line, plus access logs with latency.
- **Tested** — unit + integration + API tests running the full ASGI stack, with
  a **90 %+ coverage gate** enforced in CI.

## Architecture

```
app/
  api/v1/         presentation layer — routers, request/response wiring
  services/       business logic — aggregation, auth, price monitoring
  domain/         entities, value objects (Money), provider ports (interfaces)
  providers/      external API adapters + the resilient HTTP client
  repositories/   data access (SQLAlchemy)
  resilience/     circuit breaker, cache
  db/             engine, session, ORM models
  core/           config, security, logging, errors, middleware, rate limiting
  workers/        Celery app + tasks (price monitoring, cleanup)
  container.py    composition root (dependency injection)
  main.py         application factory
```

Dependencies point inward through interfaces: routers depend on services,
services depend on ports, and only adapters know about a concrete vendor.
Adding a new provider is a registry change, not a rewrite.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the layer diagram and
request flow.

## API

| Method | Path | Auth | Description |
| ------ | ---- | ---- | ----------- |
| POST | `/api/v1/auth/register` | – | Create an account (sends verification) |
| POST | `/api/v1/auth/login` | – | Obtain access + refresh tokens |
| POST | `/api/v1/auth/refresh` | – | Exchange a refresh token |
| POST | `/api/v1/auth/logout` | bearer | Revoke the current access/refresh token |
| POST | `/api/v1/auth/verify-email` | – | Confirm an email with a verification token |
| POST | `/api/v1/auth/resend-verification` | – | Re-send the verification email |
| POST | `/api/v1/auth/password-reset/request` | – | Request a reset token by email |
| POST | `/api/v1/auth/password-reset/confirm` | – | Set a new password with a reset token |
| GET | `/api/v1/auth/me` | bearer | Current profile |
| GET | `/api/v1/flights/search` | optional | Aggregated, ranked flight search |
| GET | `/api/v1/weather` | – | Forecast for a location & date |
| GET | `/api/v1/currency/convert` | – | Currency conversion |
| POST/GET/DELETE | `/api/v1/price-alerts` | bearer | Manage price alerts |
| GET | `/api/v1/admin/metrics` | admin | Dashboard metrics |
| GET | `/api/v1/health/live`, `/ready` | – | Probes |
| GET | `/metrics` | – | Prometheus exposition (RED metrics per route) |

Interactive docs are served at `/docs` (Swagger) and `/redoc` when the app runs.

### Example

```bash
curl "http://localhost:8000/api/v1/flights/search?origin=THR&destination=IST&departure_date=2026-08-10&sort=price"
```

```json
{
  "data": [
    {
      "id": "fl_1a2b...", "airline": "Turkish Airlines", "stops": 0,
      "departure_time": "2026-08-10T06:20:00Z", "duration_minutes": 165,
      "price": { "amount_minor": 12900, "currency": "USD" },
      "provider": "globehop", "score": 0.92
    }
  ],
  "page": { "next_cursor": null, "has_more": false },
  "meta": { "degraded": false, "providers_ok": 2, "providers_failed": 0, "total": 7 }
}
```

## Quick start

### Local (Python 3.12+)

```bash
make install                 # create .venv and install deps
cp .env.example .env         # then edit SECRET_KEY etc.
make test                    # run the suite with the coverage gate
make run                     # start uvicorn on :8000
```

Out of the box the app uses SQLite and an in-memory cache, so it runs with no
external services. Point `DATABASE_URL`/`REDIS_URL` at Postgres/Redis for a
production-like setup.

### Docker

```bash
docker compose up --build
```

This starts the API, a Celery worker+beat, PostgreSQL and Redis.

## Providers

Real inventory (flights/hotels) sits behind paid APIs; those adapters plug into
the same ports as the bundled deterministic sample provider, which lets the
whole pipeline run and be tested without credentials. Free adapters are wired
for weather (Open-Meteo) and currency (exchangerate.host). Recommended
production providers: Amadeus (flights/hotels), OpenWeatherMap, Open Exchange
Rates, OpenRouteService.

## Testing & quality

```bash
make lint      # ruff
make type      # mypy (strict-ish)
make test      # pytest + coverage (fails under 90%)
```

The suite exercises security (hashing, tokens), resilience (circuit breaker,
retries, cache), the aggregation algorithm, and every endpoint through the real
ASGI stack against an isolated SQLite database.

## Notes on scope

- **Booking & payment are intentionally out of scope** — the platform searches,
  aggregates, plans and alerts; it never charges a card (no PCI-DSS surface).
- The admin dashboard is exposed as JSON metrics intended for a separate SPA.
- Python 3.14 is the aspirational target from the original brief; the code
  targets 3.12+ and runs on it today.

## License

MIT
