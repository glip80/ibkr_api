# IBKR MCP Service Architecture

## Overview

**IBKR MCP Service** is a Model Context Protocol (MCP) server that exposes Interactive Brokers (IBKR) market data tools to AI clients. It provides historical quotes, fundamental data, and earnings information with PostgreSQL caching and background synchronization.

### Key Characteristics

- **Protocol**: MCP (Model Context Protocol) over stdio
- **Data Source**: Interactive Brokers API via `ib_async`
- **Persistence**: PostgreSQL with SQLAlchemy async ORM
- **Background Processing**: Periodic cache refresh via SyncManager

---

## Functional Areas

### 1. Services Layer (`src/ibkr_mcp_service/services/`)

| Component | Responsibility |
|-----------|----------------|
| **IBKRClient** | Manages IB connection lifecycle with exponential backoff retry logic. Thread-safe API calls via asyncio Lock. |
| **QuoteService** | Orchestrates historical quote fetching using cache-first strategy. Fetches from IBKR on cache miss, persists to DB. |
| **FundamentalsService** | Handles fundamental data and earnings XML fetching from IBKR. |

### 2. Database Layer (`src/ibkr_mcp_service/db/`)

| Component | Responsibility |
|-----------|----------------|
| **base.py** | SQLAlchemy async engine and session factory setup |
| **orm_models.py** | ORM models: `OHLCVBarORM`, `EarningsORM`, `FundamentalsORM` |
| **repository.py** | Data access repositories: `QuoteRepository`, `EarningsRepository`, `FundamentalsRepository` |

### 3. Domain Models (`src/ibkr_mcp_service/models/`)

Request/Response models and enums:
- `QuoteRequest` / `QuoteResponse` - Historical OHLCV data
- `EarningsRequest` / `EarningsResponse` - Earnings calendar
- `FundamentalsRequest` / `FundamentalsResponse` - Financial fundamentals
- Enums: `BarSize`, `SecType`, `WhatToShow`

### 4. MCP Tools (`src/ibkr_mcp_service/tools/`)

Exposes services via MCP protocol:
- `get_quotes` - Historical OHLCV bars
- `get_fundamentals` - Financial summary XML
- `get_earnings` - Earnings calendar XML

### 5. Sync Manager (`src/ibkr_mcp_service/sync/`)

**SyncManager** runs a background loop that:
1. Discovers all unique symbol combinations from the database
2. Refreshes each symbol's data via QuoteService
3. Respects configured sync interval and lookback period

### 6. Configuration (`src/ibkr_mcp_service/config.py`)

**Settings** class using Pydantic for environment-based configuration (IBKR host/port, sync interval, database connection).

---

## Key Execution Flows

### Flow 1: Get Quotes (Primary Use Case)

```
MCP Client → call_tool("get_quotes")
    ↓
QuoteService.get_quotes()
    ↓
[Cache Check] → QuoteRepository.get_bars()
    ├─ Cache Hit → Return cached QuoteResponse
    └─ Cache Miss → IBKRClient.get_historical_data()
                      ↓
                    QuoteRepository.upsert_bars()
                      ↓
                    Return fresh QuoteResponse
```

**Steps**:
1. MCP tool invokes `QuoteService.get_quotes()` with `QuoteRequest`
2. Repository checks PostgreSQL for existing bars
3. On cache hit: return immediately with `cached=True`
4. On cache miss: call `IBKRClient.get_historical_data()`
5. Transform raw bars to domain models
6. Persist to database via upsert
7. Return `QuoteResponse` with `cached=False`

### Flow 2: Background Sync

```
SyncManager.run_forever() [loop]
    ↓
_sync_all()
    ↓
Query distinct symbol combinations from OHLCVBarORM
    ↓
For each symbol:
    QuoteService.get_quotes() [same as Flow 1]
    ↓
Log refresh status
```

**Behavior**:
- Runs on configurable interval (default: 3600 seconds)
- Fetches fresh data for all cached symbols
- Uses configurable lookback duration (default: 30 days)
- Continues on per-symbol failures (logs and proceeds)

### Flow 3: Application Startup

```
main() [entry point]
    ↓
asyncio.run(_async_main())
    ↓
configure_logging()
    ↓
_startup() → IBKRClient.connect() [with retry]
    ↓
SyncManager.run_forever() [background task]
    ↓
run_mcp_server() [blocks - serves MCP stdio]
    ↓
[On shutdown] stop sync, disconnect IBKR
```

---

## Architecture Diagram

```mermaid
graph TB
    subgraph "MCP Client"
        MC[MCP Tools]
    end

    subgraph "ibkr_mcp_service"
        subgraph "Tools Layer"
            MT[mcp_tools.py]
        end

        subgraph "Services Layer"
            QS[QuoteService]
            FS[FundamentalsService]
            IC[IBKRClient]
        end

        subgraph "Database Layer"
            QR[QuoteRepository]
            ER[EarningsRepository]
            FR[FundamentalsRepository]
            ORM[ORM Models]
            DB[(PostgreSQL)]
        end

        subgraph "Domain Models"
            DM[Request/Response Models<br/>BarSize, SecType, WhatToShow Enums]
        end

        subgraph "Sync"
            SM[SyncManager]
        end

        subgraph "Config"
            CFG[Settings]
        end
    end

    subgraph "External"
        IB[Interactive Brokers<br/>TWS/Gateway]
    end

    MC --> MT
    MT --> QS
    MT --> FS
    QS --> QR
    QS --> IC
    FS --> FR
    FS --> IC
    QR --> ORM
    ER --> ORM
    FR --> ORM
    ORM --> DB
    SM --> QS
    SM --> QR
    IC --> IB
    QS --> DM
    FS --> DM
    CFG --> IC
    CFG --> SM
```

---

## Data Flow Summary

| Operation | Path |
|-----------|------|
| Get Quotes | MCP → QuoteService → [Cache → DB] or [IBKR → DB] |
| Get Fundamentals | MCP → FundamentalsService → IBKRClient → IBKR |
| Get Earnings | MCP → FundamentalsService → IBKRClient → IBKR |
| Background Sync | SyncManager → QuoteService → [Cache refresh] |

---

## Configuration

Key settings (via environment or `.env`):

| Setting | Description | Default |
|---------|-------------|---------|
| `IBKR_HOST` | TWS/Gateway host | `127.0.0.1` |
| `IBKR_PORT` | TWS: 7497, Gateway: 4001 | `7497` |
| `IBKR_CLIENT_ID` | Unique connection ID | `1` |
| `IBKR_TIMEOUT` | Connect timeout (seconds) | `30` |
| `DATABASE_URL` | PostgreSQL connection | `postgresql+asyncpg://ibkr:password@localhost:5432/ibkr_mcp` |
| `SYNC_INTERVAL_SECONDS` | Background sync cadence | `300` |
| `SYNC_LOOKBACK_DAYS` | Historical window on refresh | `365` |
| `LOG_LEVEL` | `DEBUG`/`INFO`/`WARNING` | `INFO` |
| `LOG_FORMAT` | `json` or `console` | `json` |

---

## Testing Strategy

- **Unit Tests** (`tests/unit/`): Domain models, QuoteService logic, Repository methods
- **Integration Tests** (`tests/integration/`): DB operations, IB connection

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `ib_async` | IBKR API wrapper |
| `mcp` | MCP server SDK |
| `sqlalchemy[asyncio]` | Async ORM |
| `asyncpg` | Async PostgreSQL driver |
| `pydantic-settings` | Configuration management |
| `structlog` | Structured logging |
| `tenacity` | Retry logic |
| `alembic` | Database migrations |

---

## Key Design Decisions

### Cache-First with Async Upsert
Every live IBKR response is immediately stored using PostgreSQL `INSERT ... ON CONFLICT DO UPDATE`, ensuring idempotent writes and no duplicate rows even when the sync loop and an MCP call race.

### Single ib_async Connection with asyncio.Lock
`ib_async` multiplexes over one TCP socket to TWS/Gateway; the lock prevents concurrent `reqHistoricalData` calls from interleaving responses.

### Tenacity Retry on Connect
IBKR's gateway can take a few seconds to accept connections; three attempts with exponential back-off cover transient failures without blocking the MCP server indefinitely.

### Alembic for Migrations
Schema changes are version-controlled and applied automatically in the Docker `ENTRYPOINT` before the server starts, so the DB is always in sync with the code.

### uv as Package Manager
`uv venv` + `uv pip install` replaces pip/poetry for significantly faster dependency resolution and lock-file generation.

---

## Folder Structure

```
ibkr-mcp-service/
├── src/ibkr_mcp_service/
│   ├── config.py               # Pydantic Settings
│   ├── logging_config.py       # structlog setup
│   ├── main.py                 # Entry point
│   ├── models/
│   │   └── domain.py           # Pydantic request/response models
│   ├── db/
│   │   ├── base.py             # Engine + session factory
│   │   ├── orm_models.py       # SQLAlchemy table definitions
│   │   └── repository.py       # CRUD data access layer
│   ├── services/
│   │   ├── ibkr_client.py      # ib_async wrapper with retry
│   │   ├── quote_service.py    # Historical quote logic
│   │   └── fundamentals_service.py  # Fundamental + earnings logic
│   ├── sync/
│   │   └── sync_manager.py     # Background refresh loop
│   └── tools/
│       └── mcp_tools.py        # MCP server + tool definitions
├── alembic/                    # DB migrations
├── tests/
│   ├── unit/                   # No external deps needed
│   └── integration/            # Requires PostgreSQL
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml              # uv / hatchling build
```

---

## ASCII Architecture Diagram

```
┌─────────────────────────────────────────────┐
│              MCP Client (LLM / IDE)          │
└────────────────────┬────────────────────────┘
                     │ stdio (JSON-RPC)
┌────────────────────▼────────────────────────┐
│   tools/mcp_tools.py  (MCP Server)           │
│   get_quotes · get_fundamentals · get_earnings│
└──────────┬─────────────────┬────────────────┘
           │                 │
    ┌──────▼──────┐   ┌──────▼──────────┐
    │QuoteService │   │FundamentalsService│
    └──────┬──────┘   └──────┬──────────┘
           │                 │
    ┌──────▼─────────────────▼──────┐
    │     services/ibkr_client.py    │  ← ib_async IB()
    │     (retry, lock, reconnect)   │
    └──────┬────────────────────────┘
           │
    ┌──────▼──────────────────────┐
    │   db/repository.py           │  ← upsert + select
    │   PostgreSQL via SQLAlchemy  │
    └──────────────────────────────┘
           ↑
    ┌──────┴──────────────────────┐
    │   sync/sync_manager.py       │  ← asyncio background task
    │   (periodic refresh loop)     │
    └──────────────────────────────┘
``` |