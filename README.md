# IBKR MCP Service

MCP server exposing Interactive Brokers market data as AI tools, backed by **PostgreSQL** via **SQLAlchemy 2.0 async ORM**.

## Tools

| Tool | Description | Key Defaults |
|---|---|---|
| `get_quotes` | Historical OHLCV bars | `duration="1 Y"`, `bar_size="1 day"`, `what_to_show="ADJUSTED_LAST"`, `use_rth=True` |
| `get_fundamentals` | Financial summary XML | `report_type="ReportsFinSummary"` |
| `get_earnings` | EPS / analyst estimates XML | RESC report |
| `get_sync_log` | Inspect recent sync activity | `limit=50` |
| `trigger_sync` | Force immediate refresh | `data_type="all"` |

## Architecture

```
MCP Client
    │  stdio
    ▼
server.py (MCP Server)
    │
    ├── ibkr_client.py   ← ib_async wrapper
    ├── persistence.py   ← cache-first data access (TTL-aware)
    ├── database.py      ← SQLAlchemy engine + session factory
    ├── models.py        ← ORM models (Mapped / mapped_column style)
    ├── sync.py          ← background asyncio sync scheduler
    └── config.py        ← all settings from env vars

PostgreSQL
    └── Tables: quotes, fundamentals, earnings, sync_log
```

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 14+
- TWS or IB Gateway (paper trading: port 7497)

### Local Setup

```bash
git clone <repo>
cd ibkr-mcp-service

# Create virtual environment
python -m venv .venv && source .venv/bin/activate

# Install (including dev extras)
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env — set IBKR_PORT and POSTGRES_PASSWORD

# Start PostgreSQL (or use docker-compose for just postgres)
docker compose up postgres -d

# Run database migrations
alembic upgrade head

# Start the MCP server
python -m ibkr_mcp.server
```

### Docker (full stack)

```bash
cp .env.example .env   # edit POSTGRES_PASSWORD, IBKR_PORT

docker compose up -d
# Starts: postgres → alembic migrate → ibkr-mcp
```

## Database Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Generate a new migration after changing models.py
alembic revision --autogenerate -m "add new column"

# Downgrade one step
alembic downgrade -1
```

## Testing

```bash
# Unit tests — no PostgreSQL or TWS required (uses in-memory SQLite)
pytest tests/unit/ -v

# Integration tests — requires PostgreSQL + running TWS
export TEST_DATABASE_URL="postgresql+asyncpg://ibkr:ibkr@localhost:5432/ibkr_mcp_test"
pytest tests/integration/ -v --run-integration
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://ibkr:ibkr@localhost:5432/ibkr_mcp` | Full SQLAlchemy async URL |
| `DB_ECHO` | `false` | Log all SQL statements |
| `IBKR_HOST` | `127.0.0.1` | TWS / IB Gateway host |
| `IBKR_PORT` | `7497` | 7497 paper \| 7496 live \| 4001 gateway |
| `IBKR_CLIENT_ID` | `1` | Must be unique per simultaneous connection |
| `IBKR_TIMEOUT` | `30` | Request timeout in seconds |
| `QUOTES_TTL_HOURS` | `1` | Quote cache TTL |
| `FUNDAMENTALS_TTL_HOURS` | `24` | Fundamental cache TTL |
| `SYNC_WATCHLIST` | _(empty)_ | Comma-separated tickers for background sync |
| `SYNC_INTERVAL_SECONDS` | `3600` | Background sync interval |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_FORMAT` | `text` | `text` (dev) or `json` (production) |

## TWS Prerequisites

**Edit → Global Configuration → API → Settings**
- Enable ActiveX and Socket Clients
- Socket port: `7497` (paper) or `7496` (live)
- Allow connections from localhost (or Docker gateway: `172.17.0.1`)
