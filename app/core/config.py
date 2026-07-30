"""Typed application settings loaded from the environment (12-factor).

Everything the app needs to run is declared here once, validated at import
time, and injected wherever required. Missing or malformed values fail fast
on startup instead of surfacing as obscure runtime errors later.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]

# Shipping default — usable for local dev, refused in production (see validator below).
INSECURE_DEFAULT_SECRET = "change-me-in-production-please-32-chars-min"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- general -----------------------------------------------------------
    app_name: str = "Smart Travel Aggregator"
    environment: Environment = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # --- security ----------------------------------------------------------
    secret_key: str = Field(
        default=INSECURE_DEFAULT_SECRET,
        min_length=32,
        description="Signing key for JWTs; override in every real environment.",
    )
    jwt_algorithm: str = "HS256"
    access_token_ttl: int = 900  # 15 minutes
    refresh_token_ttl: int = 60 * 60 * 24 * 14  # 14 days
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # --- persistence -------------------------------------------------------
    database_url: str = "sqlite+aiosqlite:///./smart_travel.db"
    redis_url: RedisDsn | None = None

    # --- rate limiting -----------------------------------------------------
    rate_limit_per_minute: int = 120

    # --- external providers -----------------------------------------------
    weather_base_url: str = "https://api.open-meteo.com/v1"
    currency_base_url: str = "https://api.exchangerate.host"
    http_timeout_seconds: float = 5.0
    http_max_retries: int = 2
    provider_cache_ttl: int = 300

    # ----------------------------------------------------------------------
    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        # Allow a comma-separated string in the .env file for convenience.
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _refuse_default_secret_in_production(self) -> Settings:
        if self.environment in ("staging", "production") and (
            self.secret_key == INSECURE_DEFAULT_SECRET
        ):
            raise ValueError(
                "SECRET_KEY must be set to a unique value in staging/production; "
                "the shipped default is not allowed."
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def sqlalchemy_url(self) -> str:
        # PostgresDsn is normalised to a str; SQLite passes straight through.
        return str(self.database_url)


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance (one parse per process)."""
    return Settings()
