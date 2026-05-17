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
IBKR's gateway can take a few seconds to access; exponential backoff prevents burst failures from TWS hanging on reconnect.

### Async/Async SessionFactory
Asynchronous IBKR calls require non-blocking MCP server; `asyncio.run()` wraps `main()` with `AsyncSession` and `AsyncEngine`.

### Session Isolation per Sync Cycle
New `AsyncSession()` created per `_sync_all()` call to prevent transaction contamination across symbol discovery.

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| **Runtime** | Python 3.11+ |
| **Async Runtime** | asyncio |
| **Data Source** | Interactive Brokers (TWS/Gateway) via `ib_insync` |
| **ORM** | SQLAlchemy 2.0 (async) |
| **Database** | PostgreSQL |
| **Protocol** | MCP (Model Context Protocol) over stdio |
| **Logging** | structlog (JSON structured) |
| **Retry** | tenacity (exponential backoff) |
| **Config** | Pydantic settings |
| **Migration** | Alembic |
| **Package Manager** | uv (fast Python package installer) |

---

## Structure

```
src/ibkr_mcp_service/
├── main.py                     # Async entry point
├── config.py                   # Pydantic Settings
├── logging_config.py           # Structlog configuration
├── tools/
│   └── mcp_tools.py           # Server + 3 tool definitions
├── services/
│   ├── ibkr_client.py         # ib_async wrapper, retries, locks
│   ├── quote_service.py       # Cache-first OHLCV orchestration
│   └── fundamentals_service.py # Cache-first XML orchestration
├── sync/
│   └── sync_manager.py        # Background sync loop, symbol discovery
├── models/
│   └── domain.py              # Request/response DTOs + enums
└── db/
    ├── base.py                # Async engine, session factory
    ├── repository.py          # Async CRUD repositories
    └── orm_models.py          # Database tables (constrained)
```

---

## Component Details

### IBKR Client (`services/ibkr_client.py`)

**Purpose**: Wraps `ibasync.IB` for TWS/Gateway connection with safety features.

**Critical Methods:**
```python
async def connect() -> None
# • Exponential backoff retries (3 attempts)
# • Logs connection details (host/port)
# • Waits for isConnected()

async def get_historical_data() -> BarDataList
# • Thread-safe via asyncio.Lock
# • Handles concurrent quote requests
# • IMPORTANT: ib_async multiplexes over ONE socket

async def disconnect() -> None
# • Safe cleanup, logs disconnection
```

**Connection Safety:**
- Single `IBKRClient` instance (singleton pattern)
- Lock for `reqHistoricalDataAsync` to prevent response interleaving
- Retry with `tenacity` decorator (`stop_after_attempt(3)`, `wait_exponential`)

### Quote Service (`services/quote_service.py`)

**Purpose**: Business logic for historical OHLCV fetching with caching.

**Cache Strategy:**
```python
async def get_quotes(req: QuoteRequest, force_refresh: bool = False) -> QuoteResponse
# 1. Check DB: QuoteRepository.get_bars()
# 2. On cache hit → return QuoteResponse(cached=True)
# 3. On cache miss/cached=False:
#    a. Call IBKRClient.get_historical_data()
#    b. Transform BarDataList → OHLCVBar objects
#    c. Persist via QuoteRepository.upsert()
#    d. Return QuoteResponse(cached=False)
```

**Unique Constraint**: `(symbol, sec_type, currency, bar_size, what_to_show, adjusted, bar_date)`

### Fundamentals Service (`services/fundamentals_service.py`)

**Purpose**: Fetches and caches fundamental XML data.

**Two Data Types:**
```python
# Financial fundamentals (XML)
async def get_fundamentals(req: FundamentalsRequest, force_refresh: bool = False) -> FundamentalsResponse
# Constraint: (symbol, report_type)

# Earnings calendar (XML)
async def get_earnings(req: EarningsRequest, force_refresh: bool = False) -> EarningsResponse
# Constraint: (symbol)
```

**XML Parsing**: IBKR returns raw XML string; clients must parse with `xml.dom.minidom` or similar.

### Sync Manager (`sync/sync_manager.py`)

**Purpose**: Background refresh loop that discovers all symbols and updates them.

**Discovery Pattern:**
```python
async def _sync_all():
    # 1. Get all symbols from each table
    ohlcv_keys = await _get_ohlcv_keys(session)
    fund_keys = await _get_fundamentals_keys(session)
    earn_symbols = await _get_earnings_symbols(session)

    # 2. Loop through each key, refresh via services
    for row in ohlcv_keys:
        # Calls QuoteService, bypassing read cache (services skip DB on write path)
        pass

    # 3. Graceful error handling: log, continue to next symbol
```

**Symbol Discovery Queries:**
- `SELECT symbol FROM ohlcv_bars WHERE symbol IS NOT NULL`
- `SELECT DISTINCT symbol, currency FROM fundamentals WHERE symbol IS NOT NULL`
- `SELECT DISTINCT symbol FROM earnings WHERE symbol IS NOT NULL`

**Shutdown Signal:** `stop()` sets `self._running = False`; loop exits after current cycle.

### MCP Tools (`tools/mcp_tools.py`)

**Server Setup:**
```python
server = Server("ibkr-mcp")

# Transport: stdio (MCP over stdin/stdout)
async def run_mcp_server():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
```

**Tool Definitions:**
| Tool | Description | Inputs |
|------|-------------|--------|
| `get_quotes` | Historical OHLCV bars (for AI price analysis) | symbol, duration (30 D/365 D), bar_size, what_to_show, adjusted |
| `get_fundamentals` | Financial summary XML (per-symbol) | symbol, report_type (SUMMARY/IFINANCE) |
| `get_earnings` | Earnings calendar XML (full calendar) | symbol |

### Database Layer (`db/`)

**Session Factory:**
```python
# base.py
async_engine = create_async_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
)
session_factory = sessionmaker(autocommit=False, autoflush=False, class_=AsyncSession)
```

**Repositories (No ORM for CRUD):**
```python
class QuoteRepository:
    async def get_bars(...) -> List[OHLCVBarORM] | None
    async def upsert(...)  # INSERT ... ON CONFLICT

class FundamentalsRepository:
    async def get(...) -> FundamentalsORM | None
    async def upsert(...)  # INSERT ... ON CONFLICT

class EarningsRepository:
    async def get(...) -> EarningsORM | None
    async def upsert(...)  # INSERT ... ON CONFLICT
```

**Why No ORM for CRUD?**
- Faster queries with explicit SQL
- Better control over `INSERT ... ON CONFLICT` syntax
- Easier upsert logic without model binding

### Domain Models (`models/domain.py`)

**Request/Response DTOs:**
```python
# Enums
class SecType(str, Enum)
  • STK (stock), OPT (option), FUT (futures)

class BarSize(str, Enum)
  • 1 second, 5 seconds, 1 minute, 1 hour, 1 day, 1 year

class WhatToShow(str, Enum)
  • TRADES, BID, ASK, MIDPOINT, VOLATILITY, FALSEARAM, ADJUSTED_LAST

# Request DTOs
QuoteRequest, FundamentalsRequest, EarningsRequest

# Response DTOs
QuoteResponse(cached: bool, bars: List[OHLCVBar])
FundamentalsResponse(cached: bool, xml_str)
EarningsResponse(cached: bool, xml_str)
```

**ORM Models (for constraint validation only):**
- `OHLCVBarORM` - Table with unique constraint
- `FundamentalsORM` - Table with unique constraint
- `EarningsORM` - Table with unique constraint

---

## Deployment

### Prerequisites

- **IBKR TWS** (Paper trading) or **IBKR Gateway** (Live trading) running on port `7497` (TWS) or `4001` (Gateway)
- **PostgreSQL** instance (Docker recommended)
- **Docker** + **docker-compose** OR **Python 3.11+** with `uv` (fastest Python installer)

### Configuration

Set environment variables or `.env` file:

```bash
# IBKR connection
IBKR_HOST=127.0.0.1
IBKR_PORT=7497           # 4001 for Gateway, 7497 for TWS
IBKR_CLIENT_ID=1
IBKR_TIMEOUT=30

# Database
DATABASE_URL=postgresql+asyncpg://ibkr:password@localhost:5432/ibkr_mcp

# Sync
SYNC_INTERVAL_SECONDS=3600    # Refresh every 1 hour
SYNC_LOOKBACK_DAYS=365        # Get last 365 days on refresh

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json  # console for human-readable
```

### Running Methods

**Option 1: Docker Compose (Recommended)**
```bash
docker compose up
```

**Option 2: Python Direct**
```bash
# Using pyproject.toml entrypoint:
python -m ibkr_mcp_service.main

# Standalone sync script:
python -m ibkr_mcp_service.scripts.run_sync
```

**Option 3: Development with uv**
```bash
uv sync
export $(cat .env | xargs)
uv run python -m ibkr_mcp_service.main
```

### Docker Setup

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ibkr
      POSTGRES_PASSWORD: password
      POSTGRES_DB: ibkr_mcp
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  ibkr-api:
    build: .
    environment:
      IBKR_PORT: 7497
      DATABASE_URL: postgresql+asyncpg://ibkr:password@postgres:5432/ibkr_mcp
    ports:
      - "3000:3000"
    depends_on:
      - postgres

volumes:
  postgres_data:
```

---

## Testing

### Test Organization

```
tests/
├── unit/                      # Isolated component tests
│   ├── test_quote_service.py    # QuoteService cache logic
│   ├── test_fundamentals_service.py  # HTTP/XML parsing
│   ├── test_ibkr_client.py      # Connect/disconnect/retry
│   └── test_repository.py       # DB upsert/query
├── integration/               # End-to-end tests
│   ├── test_ib_connection.py    # Real IBKR connection
│   └── test_db_integration.py   # PostgreSQL + services
└── conftest.py                # Pytest fixtures (session factory, IBKR mock, etc.)
```

### Key Test Coverage

- ✅ **QuoteService**: Cache hit/miss with `force_refresh=False`
- ✅ **FundamentalsService**: Cache hit/miss, XML parsing
- ✅ **Earnings cache**: Symbol lookup, XML return
- ✅ **IBKRClient**: Connect/disconnect, retry logic
- ✅ **SyncManager**: Symbol discovery, loop control
- ✅ **DB upsert**: Unique constraint handling (`ON CONFLICT`)
- ✅ **Async clean shutdown**: Task cancellation, session close

### Running Tests

```bash
# Tests installed via uv:
uv run pytest

# With coverage:
uv run pytest --cov

# Specific test file:
uv run pytest tests/unit/test_quote_service.py
```

---

## Design Decisions & Tradeoffs

### 1. Cache-First Strategy
**Why**: Reduce IBKR API calls, improve latency for AI clients.
**How**: Check DB before IBKR for reads; sync loop writes bypass read cache.
**Tradeoff**: Initial load (first query for a symbol) is slower; mitigated by background sync.

### 2. Async/Async SessionFactory
**Why**: Asynchronous IBKR calls, non-blocking MCP server.
**How**: `asyncio.run()` wraps `main()`, `AsyncSession` with `AsyncEngine`.
**Tradeoff**: More complex error handling; requires async-aware test setup.

### 3. Session Isolation per Sync Cycle
**Why**: Prevent transaction contamination across symbol discovery.
**How**: New `AsyncSession()` created per `_sync_all()` call.
**Tradeoff**: Minor overhead on very large syncs (rare in practice).

### 4. No ORM for CRUD Operations
**Why**: Faster queries with explicit SQL, better control over `INSERT ... ON CONFLICT`.
**How**: Repository layer uses raw SQL; ORM models only for constraint validation.
**Tradeoff**: More boilerplate code; easier to refactor later if ORM needed.

### 5. Structlog for Observability
**Why**: Structured logging for tracing across async boundaries.
**How**: All async functions log with `log.info()`, exception logging with `log.exception()`.
**Tradeoff**: Larger logs than plain print; better machine readability.

### 6. Token-Based Unique Constraints (NOT auto-increment PK)
**Why**: Financial data identifies by trading symbols, not internal IDs.
**How**: Unique constraint on `(symbol, report_type)` ensures no dups; PK is internal auto-increment.
**Tradeoff**: Manual security checks required for symbol injection; mitigated by input validation.

---

## Constraints & Gotchas

### IBKR Limitations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| **Rate limits** | High bar count = slow requests | Configurable `duration_str` bars per request; sync refreshes entire lookback |
| **TWS vs Gateway** | Different ports (`7497` vs `4001`) | Environment variable `IBKR_PORT` with defaults |
| **Connection instability** | TWS/Gateway may crash on internet issues | Exponential backoff retries; sync loop will retry on next interval |
| **Symbol list** | Symbols not auto-discovered from IBKR account | Manual DB population or script; sync discovers existing symbols |

### Database Constraints

| Constraint | Table | Columns |
|------------|-------|---------|
| **Unique** | `ohlcv_bars` | `(symbol, sec_type, currency, bar_size, what_to_show, adjusted, bar_date)` |
| **Unique** | `fundamentals` | `(symbol, report_type)` |
| **Unique** | `earnings` | `(symbol)` |
| **Index** | All tables | `symbol` column for quick discovery |

**Performance**: Index lookups on `symbol + bar_date` for cache hits; `symbol + report_type` for fundamentals.

### Async Gotchas

| Gotcha | Explanation | Mitigation |
|--------|-------------|------------|
| **Running background tasks** | Must cancel on shutdown | `sync_task.cancel()`, `finally:` block in `_async_main()` |
| **Session non-transactional** | Services bypass begin() scope | Repositories manage their own transaction; sync uses explicit close |
| **Lock contention** | IBKR client lock protects concurrent requests | Lock acquired per request; default unlimited timeout (use carefully) |
| **No pgBouncer** | Single PostgreSQL instance assumed | Existing setup works for single-server deployment; add pgBouncer for scaling |

---

## Future Enhancements

### High-Priority

- [ ] **Symbol auto-discovery** from IBKR account via `reqSecDefOptParamsAsync`
- [ ] **Multi-user session support** (per-client cache isolation)
- [ ] **Connection pooling** with pgBouncer for database scale out
- [ ] **Prometheus metrics** for sync progress and latency tracking

### Medium-Priority

- [ ] **Additional IBKR feeds**: Trades, quotes, order book, volatility index
- [ ] **Custom TTL caching** instead of interval-based sync
- [ ] **WebSocket real-time feed** for intraday updates
- [ ] **AI tool wrappers**: Pre-parse XML to JSON for easier AI consumption

### Low-Priority

- [ ] **Backtesting mode**: Export historical data with dates
- [ ] **Alerts**: Notify on significant price changes
- [ ] **Options chain data**: Full option expiration hierarchy
- [ ] **Multi-asset support**: Commodities, FX, futures

---

## References & Resources

- **MCP Protocol Spec**: https://modelcontextprotocol.io/ (stdio transport)
- **ib_async Documentation**: https://github.com/JochenWaldmann/ib_insync
- **SQLAlchemy Async ORM**: https://docs.sqlalchemy.org/en/14/orm/extensions/asyncio.html
- **Interactive Brokers API**: https://interactivebrokers.github.io/
- **Project Repository**: https://github.com/glip80/ibkr_api
- **uv Documentation**: https://github.com/astral-sh/uv
- **structlog Documentation**: https://www.structlog.org/

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-05-16 | Initial architecture documentation |ept connections; three attempts with exponential back-off cover transient failures without blocking the MCP server indefinitely.

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