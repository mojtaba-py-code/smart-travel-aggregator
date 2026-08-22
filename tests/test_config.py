"""Settings validation, including the production secret-key guard."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import INSECURE_DEFAULT_SECRET, Settings


def test_default_secret_allowed_in_development() -> None:
    settings = Settings(environment="development")
    assert settings.secret_key == INSECURE_DEFAULT_SECRET


def test_default_secret_refused_in_production() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(environment="production")


def test_custom_secret_accepted_in_production() -> None:
    settings = Settings(
        environment="production", secret_key="a-real-unique-production-secret-000000"
    )
    assert settings.is_production is True


def test_cors_origins_accepts_comma_separated_string() -> None:
    settings = Settings(cors_origins="http://a.com, http://b.com")
    assert settings.cors_origins == ["http://a.com", "http://b.com"]


def test_credentials_are_off_by_default() -> None:
    assert Settings().cors_allow_credentials is False


def test_wildcard_cors_with_credentials_refused_in_production() -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(
            environment="production",
            secret_key="a-real-unique-production-secret-000000",
            cors_origins="*",
            cors_allow_credentials=True,
        )


@pytest.mark.parametrize("environment", ["development", "test", "staging"])
def test_wildcard_cors_with_credentials_refused_outside_production(environment: str) -> None:
    # A wildcard origin with credentials is not a valid configuration anywhere,
    # so the guard does not wait for the production deploy to report it.
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(
            environment=environment,
            secret_key="a-real-unique-secret-value-0000000000",
            cors_origins="*",
            cors_allow_credentials=True,
        )


def test_wildcard_origins_accepted_without_credentials() -> None:
    # Only the combination is refused; "*" on its own still serves an API that
    # attaches no credentials.
    settings = Settings(cors_origins="*", cors_allow_credentials=False)
    assert settings.cors_origins == ["*"]


def test_explicit_origins_with_credentials_accepted_in_development() -> None:
    settings = Settings(
        environment="development",
        cors_origins="http://localhost:3000",
        cors_allow_credentials=True,
    )
    assert settings.cors_allow_credentials is True


def test_explicit_origins_with_credentials_accepted_in_production() -> None:
    settings = Settings(
        environment="production",
        secret_key="a-real-unique-production-secret-000000",
        cors_origins="https://app.example.com",
        cors_allow_credentials=True,
    )
    assert settings.cors_origins == ["https://app.example.com"]
