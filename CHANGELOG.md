# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

Nothing yet.

## [1.1.0] - 2026-08-22

### Added
- One-click live demo on Render's free tier through a `render.yaml` blueprint:
  SQLite plus an in-memory cache, so the whole API runs with no external
  services and no secrets to paste.
- SMTP delivery for verification and password-reset mail, selected by the
  container as soon as `SMTP_HOST` is configured.
- `TRUSTED_PROXY_CIDRS`: behind a load balancer the real caller is taken from
  `X-Forwarded-For`, and only from networks named here.
- `CORS_ALLOW_CREDENTIALS`, off by default — the API authenticates with bearer
  tokens, not cookies.
- A root route that redirects to `/docs`, so trimming the path off the demo link
  no longer lands on a 404.
- Security policy (`SECURITY.md`), Dependabot updates, a weekly CI run and a
  secret scan across the whole history.

### Changed
- GitHub Actions are pinned to commit SHAs and the workflow token is scoped to
  `contents: read`.
- Dependency floors raised past releases with published CVEs.
- The price-monitoring worker sends through the container's notifier instead of
  constructing its own.

### Fixed
- `CORS_ORIGINS` accepts a bare `*`, a comma-separated list or a JSON array from
  the environment without crashing settings parsing.
- The in-memory rate limiter forgets idle identities instead of keeping one
  entry per address it has ever seen.
- The Redis rate limiter issues `INCR` and `EXPIRE` as a single transaction, so
  an interrupted update can no longer strand a counter without a TTL and lock
  that identity out permanently.

### Security
- The SMTP notifier hands its password to the mail server only over a TLS
  channel whose certificate and hostname it verified; the context smtplib falls
  back to when none is given checks neither.
- The deployed demo no longer answers every origin with
  `Access-Control-Allow-Origin: <caller>` plus
  `Access-Control-Allow-Credentials: true`. Wildcard origins combined with
  credentials are refused outright in production.
- Rate limiting, the audit log and the access log identify the caller rather
  than the proxy in front of them, so one visitor can no longer exhaust
  everybody's quota, and a request can still be traced back to its origin — a
  forged `X-Forwarded-For` from an untrusted peer is ignored.

## [1.0.0] - 2026-07-30

### Added
- Clean, layered FastAPI application with dependency injection.
- Flight search aggregation: concurrent fan-out, de-duplication, ranking,
  cursor pagination, and graceful degradation when a provider fails.
- Hotel search (`GET /hotels/search`) aggregated behind a `HotelProvider` port,
  with de-duplication, rating/price ranking, filtering and cursor pagination.
- Weather (Open-Meteo) and currency (exchangerate.host) provider adapters.
- Authentication: registration, login, JWT access/refresh, email verification,
  password reset, and logout via a cache-backed token denylist.
- Security: Argon2id hashing, RBAC, per-client rate limiting, hardened HTTP
  headers, audit log, and a production guard on the default `SECRET_KEY`.
- Resilience: per-provider circuit breaker, retry with backoff, and caching.
- Redis-backed rate limiter and cache, selected automatically when `REDIS_URL`
  is set (falling back to the in-process implementations otherwise).
- Prometheus `/metrics` endpoint exposing per-route RED metrics (request count
  and latency histogram), with route-template labels to bound cardinality.
- Structured JSON logging with a request-id on every line.
- PostgreSQL models with Alembic migrations; Redis and Celery wiring.
- Docker + Docker Compose, and a GitHub Actions pipeline
  (ruff, mypy, pytest with a 90% coverage gate, bandit, pip-audit, image build).

### Changed
- Extracted the shared cursor pagination helpers used by both aggregators.
- `RateLimiter` is a protocol with in-memory and Redis implementations.

[Unreleased]: https://github.com/mojtaba-py-code/smart-travel-aggregator/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/mojtaba-py-code/smart-travel-aggregator/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/mojtaba-py-code/smart-travel-aggregator/releases/tag/v1.0.0
