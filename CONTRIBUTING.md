# Contributing

Thanks for taking a look. This is how I work on the project locally.

## Setup

```bash
make install          # creates .venv and installs the project + dev tools
cp .env.example .env   # then set SECRET_KEY (see below)
```

Generate a signing key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Before you push

Everything below runs in CI, so run it locally first:

```bash
make lint    # ruff check + ruff format --check
make type    # mypy
make test    # pytest with the 90% coverage gate
```

`make format` fixes lint and formatting in place.

## Conventions

- **Architecture** — keep the layer boundaries: routers call services, services
  depend on ports, only adapters touch a vendor SDK. New providers implement an
  existing port in `app/domain/ports.py` and are registered in `app/container.py`.
- **Types** — everything in `app/` is fully typed; mypy runs in strict-ish mode.
- **Money** — always `{amount_minor, currency}`, never floats.
- **Errors** — raise an `AppError` subclass; it becomes an RFC 7807 response.
- **Tests** — add tests with the change; external HTTP is mocked, never real.
- **Commits** — short imperative subject, a body explaining the *why*.

## Project layout

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the layer diagram and the
request flow.
