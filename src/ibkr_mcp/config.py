"""
Application configuration loaded from environment variables.

All settings have sensible defaults so the service works out of the box
against a local TWS paper-trading session.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    return int(os.environ.get(key, str(default)))


def _env_bool(key: str, default: bool) -> bool:
    return os.environ.get(key, str(default)).lower() in ("1", "true", "yes")


@dataclass
class Config:
    """Central configuration object.

    Environment variables
    ---------------------
    IBKR_HOST              : TWS / IB Gateway host (default 127.0.0.1)
    IBKR_PORT              : Port (default 7497 — paper TWS)
    IBKR_CLIENT_ID         : Client ID (default 1)
    IBKR_TIMEOUT           : Request timeout seconds (default 30)
    DB_PATH                : SQLite file path (default data/ibkr_cache.db)
    QUOTES_TTL_HOURS       : Quote cache TTL in hours (default 1)
    FUNDAMENTALS_TTL_HOURS : Fundamental cache TTL in hours (default 24)
    SYNC_INTERVAL_SECONDS  : Background sync interval (default 3600)
    LOG_LEVEL              : Logging level string (default INFO)
    MCP_SERVER_NAME        : MCP server identifier (default ibkr-mcp)
    """

    ibkr_host: str = field(default_factory=lambda: _env("IBKR_HOST", "127.0.0.1"))
    ibkr_port: int = field(default_factory=lambda: _env_int("IBKR_PORT", 7497))
    ibkr_client_id: int = field(default_factory=lambda: _env_int("IBKR_CLIENT_ID", 1))
    ibkr_timeout: int = field(default_factory=lambda: _env_int("IBKR_TIMEOUT", 30))

    db_path: Path = field(default_factory=lambda: Path(_env("DB_PATH", "data/ibkr_cache.db")))
    quotes_ttl_hours: int = field(default_factory=lambda: _env_int("QUOTES_TTL_HOURS", 1))
    fundamentals_ttl_hours: int = field(default_factory=lambda: _env_int("FUNDAMENTALS_TTL_HOURS", 24))

    sync_interval_seconds: int = field(default_factory=lambda: _env_int("SYNC_INTERVAL_SECONDS", 3600))

    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    mcp_server_name: str = field(default_factory=lambda: _env("MCP_SERVER_NAME", "ibkr-mcp"))


# Module-level singleton — import and use directly.
settings = Config()
