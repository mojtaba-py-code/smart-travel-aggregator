# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Prometheus `/metrics` endpoint exposing per-route RED metrics (request count
  and latency histogram), with route-template labels to bound cardinality.

## [1.0.0] - 2026-07-30

### Added
- Clean, layered FastAPI application with dependency injection.
- Flight search aggregation: concurrent fan-out, de-duplication, ranking,
  cursor pagination, and graceful degradation when a provider fails.
- Weather (Open-Meteo) and currency (exchangerate.host) provider adapters.
- Authentication: registration, login, JWT access/refresh, email verification,
  password reset, and logout via a cache-backed token denylist.
- Security: Argon2id hashing, RBAC, per-client rate limiting, hardened HTTP
  headers, audit log, and a production guard on the default `SECRET_KEY`.
- Resilience: per-provider circuit breaker, retry with backoff, and caching.
- Structured JSON logging with a request-id on every line.
- PostgreSQL models with Alembic migrations; Redis and Celery wiring.
- Docker + Docker Compose, and a GitHub Actions pipeline
  (ruff, mypy, pytest with a 90% coverage gate, bandit, pip-audit, image build).

[Unreleased]: https://github.com/mojtaba-py-code/smart-travel-aggregator/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/mojtaba-py-code/smart-travel-aggregator/releases/tag/v1.0.0
