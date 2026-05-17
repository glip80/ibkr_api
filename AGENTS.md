# IBKR API - Project Knowledge Base

**Generated:** 2026-05-16
**Commit:** b63838783c4619596d1d9c38d096230c5b1996b5
**Branch:** main

## OVERVIEW

MCP server exposing Interactive Brokers market data (quotes, fundamentals, earnings) via ib_async, PostgreSQL persistence, async cache-first strategy. Tech: Python 3.11+, SQLAlchemy async, ib_async, MCP SDK.

## STRUCTURE

```
./
├── src/ibkr_mcp_service/    # Core application
│   ├── services/           # Business logic
│   ├── db/                 # PostgreSQL layer
│   ├── sync/               # Background refresh
│   ├── tools/              # MCP tool definitions
│   └── models/             # Domain DTOs
├── tests/                   # unit/integration tests
├── alembic/                 # DB migrations
├── scripts/                 # Utilities
└── {config files}           # pyproject.toml, README, docker-compose
```

## WHERE TO LOOK

| Task | Location | Time Estimate |
|------|----------|---------------|
| What does the service do? | `README.md` | Low |
| MCP tool definitions | `src/ibkr_mcp_service/tools/mcp_tools.py` | Low |
| Quote fetching | `src/ibkr_mcp_service/services/quote_service.py` | Low |
| IBKR connection | `src/ibkr_mcp_service/services/ibkr_client.py` | Low |
| Background sync | `src/ibkr_mcp_service/sync/sync_manager.py` | Low |
| DB schema | `src/ibkr_mcp_service/db/orm_models.py` | Low |
| Test files | `tests/unit/`, `tests/integration/` | Low |
| Migration scripts | `alembic/versions/` | Low |
| Project config | `pyproject.toml` | Low |

## CONVENTIONS

- **Async everywhere**: All I/O (DB, IBKR) uses `async/await`. Never block.
- **Cache-first**: DB check before IBKR API calls unless `force_refresh=True`.
- **Singleton IBKRClient**: Single instance shared across services (thread-safe via locks).
- **Unique constraints**: Symbols + metadata key for upserts (prevents duplicates).
- **Explicit SQL**: Repositories use raw SQL for upserts; Omit ORM for CRUD (faster, more control).
- **Session factory**: Create `AsyncSession` per sync cycle, not per request.
- **Graceful shutdown**: Cancel sync task, close sessions, disconnect IBKR on exit.
- **Structured logging**: Use structlog with keys like `symbol`, `duration`, `count`.

## ANTI-PATTERNS (THIS PROJECT)

- **Never**: Block on async operations (use `await`)
- **Never**: Share a single DB session across sync cycle + queries (prevents transaction pollution)
- **Never**: Use ORM for upsert operations (loses `INSERT ... ON CONFLICT` control)
- **Never**: Deploy without Docker Compose + PostgreSQL (TWS/Gateway required)
- **Never**: Run sync directly since `run_forever()` expects docker-postgres network

## UNIQUE STYLES

- **Tool handler pattern**: MCP tools call service layers directly; no endpoint routing.
- **Repository pattern without ORM**: `QuoteRepository`, `FundamentalsRepository`, `EarningsRepository` with raw SQL.
- **Symbol discovery via NULL queries**: `_get_ohlcv_keys(session)` uses `WHERE symbol IS NOT NULL`.
- **Enum-based tool schemas**: `SecType`, `BarSize`, `WhatToShow` drive JSON schema generation.
- **Retry at connect only**: IBKR client retries connect (3 attempts, exponential backoff); operations after connect retry at service layer.

## COMMANDS

```bash
# Development
uv sync              # Install dependencies
uv run pytest        # Run tests
uv run python -m ibkr_mcp_service.main    # Entry point

# Docker
docker compose up    # Start IBKR API + PostgreSQL
docker compose logs -f  # View logs
docker compose down   # Stop

# Database
alembic revision --autogenerate -m "description"   # Create migration
alembic upgrade head   # Apply migrations
alembic downgrade -1 # Revert migration
```

## NOTES

- **TWS vs Gateway**: Different ports (7497 vs 4001). Use `IBKR_PORT` env var.
- **Cache lookback**: `SYNC_LOOKBACK_DAYS` controls historical window on sync.
- **Max config**: 365 days + configurable bar_size.
- **Large files**: Many .py files >500 lines (1.9M total lines across 70 files).
- **Symbol list**: Symbols must exist in IBKR account; not auto-discovered.
- **Unique constraints**: Check `Orm` models before inserting to avoid upsert failures.
- **Index strategy**: Symbol + bar_date/index conditions for cache hits.