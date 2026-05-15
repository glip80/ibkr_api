"""Configuration for the IBKR MCP service using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # IBKR Connection
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497  # 7497=TWS Paper, 4001=Gateway Paper
    ibkr_client_id: int = 1
    ibkr_timeout: int = 30

    # Persistence
    database_url: str = "postgresql+asyncpg://ibkr:password@localhost:5432/ibkr_mcp"

    # Sync Manager
    sync_interval_seconds: int = 300
    sync_lookback_days: int = 365

    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of the application settings."""
    return Settings()
