# IBKR MCP Service

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that
exposes **Interactive Brokers** market data as AI-callable tools via
[ib_async](https://github.com/erdewit/ib_async).

---

## Features

| Tool | Description |
|---|---|
| `get_quotes` | Historical OHLCV bars — configurable symbol, period, interval, adjusted/unadjusted |
| `get_fundamentals` | Financial summary XML (ReportsFinSummary, ReportSnapshot, …) |
| `get_earnings` | EPS history & analyst estimates (RESC XML) |
| `get_sync_log` | Inspect recent background sync activity |
| `trigger_sync` | Force immediate data refresh for a symbol |

**Key design principles**

- **Cache-first** — SQLite cache with configurable TTLs prevents hammering TWS.
- **Background sync** — optional scheduler keeps a watchlist fresh.
- **Structured logging** — JSON (production) or human-readable (dev) via env var.
- **Fully typed** — Python 3.12 type hints throughout.
- **Dockerized** — multi-stage Docker image with non-root user.

---

## Prerequisites

- Python 3.12+
- TWS (Trader Workstation) or IB Gateway running locally or accessible over the network.
- In TWS: `Edit → Global Configuration → API → Settings` → enable **Socket port** and check **Allow connections from localhost**.

---

## Quick start (local)

```bash
# 1. Clone and enter the project
cd ibkr-mcp-service

# 2. Create a virtual environment
python -m venv .venv && source .venv/bin/activate

# 3. Install with dev extras
pip install -e ".[dev]"

# 4. Copy and edit the environment file
cp .env.example .env
# Edit .env: set IBKR_PORT to match your TWS setting

# 5. Run unit tests (no TWS needed)
pytest tests/unit/ -v

# 6. Start the MCP server (connects to TWS on startup if SYNC_WATCHLIST is set)
python -m ibkr_mcp.server
```

---

## Quick start (Docker)

```bash
# Build the image
docker compose build

# Start the service (edit .env first)
docker compose up -d

# Tail logs
docker compose logs -f ibkr-mcp
```

---

## MCP Tool Reference

### `get_quotes`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `symbol` | string | **required** | Ticker, e.g. `"AAPL"` |
| `duration` | string | `"1 Y"` | Period: `"1 Y"`, `"6 M"`, `"30 D"` |
| `bar_size` | string | `"1 day"` | Granularity: `"1 day"`, `"1 hour"`, `"5 mins"` |
| `what_to_show` | string | `"ADJUSTED_LAST"` | `"ADJUSTED_LAST"` \| `"TRADES"` \| `"MIDPOINT"` |
| `use_rth` | bool | `true` | Regular trading hours only |
| `end_datetime` | string | `""` | End of period `"YYYYMMDD HH:MM:SS"`, empty = now |
| `exchange` | string | `"SMART"` | Routing exchange |
| `currency` | string | `"USD"` | Currency code |

### `get_fundamentals`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `symbol` | string | **required** | Ticker |
| `report_type` | string | `"ReportsFinSummary"` | `"ReportsFinSummary"` \| `"ReportSnapshot"` \| `"ReportsOwnership"` \| `"CalendarReport"` |
| `exchange` | string | `"SMART"` | |
| `currency` | string | `"USD"` | |

### `get_earnings`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `symbol` | string | **required** | Ticker |
| `exchange` | string | `"SMART"` | |
| `currency` | string | `"USD"` | |

### `trigger_sync`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `symbol` | string | **required** | Ticker |
| `data_type` | string | `"all"` | `"quotes"` \| `"fundamentals"` \| `"earnings"` \| `"all"` |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `IBKR_HOST` | `127.0.0.1` | TWS / IB Gateway host |
| `IBKR_PORT` | `7497` | Port (7496 live, 7497 paper, 4001 gateway) |
| `IBKR_CLIENT_ID` | `1` | Unique client ID |
| `IBKR_TIMEOUT` | `30` | Request timeout (seconds) |
| `DB_PATH` | `data/ibkr_cache.db` | SQLite file path |
| `QUOTES_TTL_HOURS` | `1` | Quote cache TTL |
| `FUNDAMENTALS_TTL_HOURS` | `24` | Fundamentals / earnings cache TTL |
| `SYNC_WATCHLIST` | _(empty)_ | Comma-separated tickers for background sync |
| `SYNC_INTERVAL_SECONDS` | `3600` | Background sync interval |
| `LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `LOG_FORMAT` | `text` | `text` \| `json` |
| `MCP_SERVER_NAME` | `ibkr-mcp` | MCP server identifier |

---

## Running Tests

```bash
# Unit tests only (no TWS needed)
pytest tests/unit/ -v

# Integration tests (requires live TWS)
pytest tests/integration/ -v --run-integration

# Full suite with coverage
pytest --cov=ibkr_mcp --cov-report=html
```

---

## One-off Sync Script

```bash
# Sync specific symbols immediately
python scripts/run_sync.py AAPL MSFT NVDA
```

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  MCP Client (AI agent / Claude Desktop)     │
└─────────────────┬───────────────────────────┘
                  │ stdio (MCP protocol)
┌─────────────────▼───────────────────────────┐
│  server.py  (MCP Server)                    │
│  ┌──────────────────────────────────────┐   │
│  │  Tool: get_quotes                    │   │
│  │  Tool: get_fundamentals              │   │
│  │  Tool: get_earnings                  │   │
│  │  Tool: get_sync_log                  │   │
│  │  Tool: trigger_sync                  │   │
│  └────────────┬─────────────────────────┘   │
│               │                             │
│  ┌────────────▼────────┐  ┌──────────────┐  │
│  │  PersistenceStore   │  │  SyncScheduler│  │
│  │  (SQLite / aiosqlite│  │  (background) │  │
│  └────────────┬────────┘  └──────┬───────┘  │
└───────────────│─────────────────│───────────┘
                │  cache miss     │ periodic
┌───────────────▼─────────────────▼───────────┐
│  IBKRClient  (ib_async)                     │
└─────────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│  TWS / IB Gateway  (localhost or network)   │
└─────────────────────────────────────────────┘
```

---

## License

MIT
