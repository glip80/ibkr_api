# Plan: MCP Service for IBKR Quotes via ib_async

## 1. Stack
- Python 3.11+
- `uv` for deps
- `ib_async` IBKR client
- `mcp` SDK server
- `pydantic` v2 models
- `sqlalchemy` 2.0 + `alembic` migrations
- `postgres` 16
- `pytest` + `pytest-asyncio`
- `docker` + `docker-compose`
- `structlog` logging

## 2. Folder Structure

```
ibkr-mcp/
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── .env.example
├── README.md
├── alembic/
│   ├── env.py
│   └── versions/
├── src/
│   └── ibkr_mcp/
│       ├── __init__.py
│       ├── main.py                  # MCP entry
│       ├── config.py                # pydantic Settings
│       ├── logging_conf.py
│       ├── models/                  # pydantic DTOs
│       │   ├── quote.py
│       │   ├── fundamental.py
│       │   └── earnings.py
│       ├── db/
│       │   ├── base.py              # SQLAlchemy declarative
│       │   ├── session.py           # async engine/session
│       │   └── entities/            # ORM tables
│       │       ├── quote.py
│       │       ├── fundamental.py
│       │       └── earnings.py
│       ├── repositories/            # CRUD
│       │   ├── quote_repo.py
│       │   ├── fundamental_repo.py
│       │   └── earnings_repo.py
│       ├── ibkr/
│       │   ├── client.py            # ib_async wrapper, connection pool
│       │   ├── quotes.py
│       │   ├── fundamentals.py
│       │   └── earnings.py
│       ├── services/                # business logic, cache-or-fetch
│       │   ├── quote_service.py
│       │   ├── fundamental_service.py
│       │   ├── earnings_service.py
│       │   └── sync_service.py      # background sync
│       ├── mcp/
│       │   ├── server.py            # register tools
│       │   └── tools/
│       │       ├── get_quote.py
│       │       ├── get_fundamental.py
│       │       └── get_earnings.py
│       └── utils/
│           └── time.py
└── tests/
    ├── unit/
    │   ├── test_models.py
    │   ├── test_repositories.py
    │   └── test_services.py
    └── integration/
        ├── test_ibkr_client.py
        ├── test_db.py
        └── test_mcp_tools.py
```

## 3. Pydantic Models (defaults)

```python
class QuoteRequest(BaseModel):
    symbol: str
    period: str = "1 M"        # ib_async durationStr
    interval: str = "1 day"    # barSizeSetting
    adjusted: bool = True
    what_to_show: str = "TRADES"
    use_rth: bool = True

class QuoteBar(BaseModel):
    symbol: str
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    adjusted: bool

class FundamentalRequest(BaseModel):
    symbol: str
    report_type: str = "ReportsFinSummary"

class EarningsRequest(BaseModel):
    symbol: str
    limit: int = 8
```

## 4. DB Schema (alembic)
- `quotes(id, symbol, ts, interval, open, high, low, close, volume, adjusted, fetched_at)` UNIQUE(symbol,ts,interval,adjusted)
- `fundamentals(id, symbol, report_type, payload JSONB, fetched_at)`
- `earnings(id, symbol, period_end, eps_actual, eps_estimate, revenue, reported_at, fetched_at)`
- index on (symbol, ts)

## 5. Cache-or-Fetch Flow
1. service receives request
2. check repo for fresh rows in range (TTL by data type)
3. missing range → call ib_async
4. upsert results
5. return merged pydantic models

## 6. Sync Process
- `sync_service` APScheduler async job
- watchlist table or env `SYNC_SYMBOLS`
- nightly job: refresh quotes + fundamentals + earnings
- manual MCP tool `sync_now(symbol)` trigger

## 7. MCP Tools exposed
- `get_quote(symbol, period, interval, adjusted)`
- `get_fundamental(symbol, report_type)`
- `get_earnings(symbol, limit)`
- `sync_symbol(symbol)`

## 8. Logging
- `structlog` JSON output
- request_id middleware in MCP handlers
- log IBKR connection events, cache hit/miss, sync jobs

## 9. Tests

**Unit** (mock ib_async + db):
- model validation/defaults
- repo upsert idempotency
- service cache hit vs miss logic

**Integration**:
- postgres testcontainer
- ib_async against IB Gateway paper account (env-gated)
- MCP tool end-to-end via stdio

## 10. Docker

`docker-compose.yml` services:
- `db` postgres:16
- `ibgw` ghcr.io/gnzsnz/ib-gateway (paper)
- `mcp` build local, depends_on db + ibgw
- volumes: pg_data
- env: `IB_HOST`, `IB_PORT=4002`, `IB_CLIENT_ID`, `DATABASE_URL`

`Dockerfile`: uv multi-stage, copy `pyproject.toml` + `uv.lock`, `uv sync --frozen`, run `python -m ibkr_mcp.main`.

## 11. Build Order
1. scaffold uv project, pyproject deps
2. config + logging
3. db base + alembic init + migrations
4. pydantic models
5. ib_async client wrapper + reconnect
6. repos + services (quotes first)
7. MCP server + tools
8. sync scheduler
9. fundamentals + earnings
10. dockerize + compose
11. tests (unit then integration)
12. README + .env.example
