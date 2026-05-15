<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# Create a python project to implement MCP service to get qoutes from ibkr via ib_Async

qoutes:
by quote, time period, inteval,adjust or not, add defaults for all
fundamental: quote
earnigns:quote

* make the persistency to data to use in later calls, add sync process
* add logging
* add unit tests \& integration tests
* make dockerized
* use pydantic models
* use as reference [https://github.com/ib-api-reloaded/ib_async](https://github.com/ib-api-reloaded/ib_async) to adjust
* use SQLAlchemy [https://alembic.sqlalchemy.org/en/latest/](https://alembic.sqlalchemy.org/en/latest/)
* postgresdb for persistency.
* organize folder stucture according to reponsibilities
• use uv for package

Let me provide the complete project structure and remaining files directly.

Here is the full project. I'll present all remaining files:

***

## `src/ibkr_mcp_service/services/fundamentals_service.py`

```python
"""Business logic for fetching and caching fundamental data."""

from datetime import datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ibkr_mcp_service.db.repository import FundamentalsRepository, EarningsRepository
from ibkr_mcp_service.models.domain import (
    FundamentalsRequest, FundamentalsResponse,
    EarningsRequest, EarningsResponse,
)
from ibkr_mcp_service.services.ibkr_client import IBKRClient

log = structlog.get_logger(__name__)


class FundamentalsService:
    """Orchestrates fundamental and earnings data fetching with DB caching."""

    def __init__(self, session: AsyncSession, ibkr: IBKRClient) -> None:
        self._fund_repo = FundamentalsRepository(session)
        self._earn_repo = EarningsRepository(session)
        self._ibkr = ibkr

    async def get_fundamentals(self, req: FundamentalsRequest) -> FundamentalsResponse:
        """Return fundamental data, using the cache when available."""
        cached = await self._fund_repo.get(req.symbol, req.report_type)
        if cached:
            log.info("cache_hit_fundamentals", symbol=req.symbol)
            return FundamentalsResponse(
                symbol=req.symbol,
                report_type=req.report_type,
                xml_data=cached.xml_data,
                cached=True,
                fetched_at=cached.fetched_at,
            )

        contract = self._ibkr.make_contract(
            symbol=req.symbol, sec_type=req.sec_type.value,
            exchange=req.exchange, currency=req.currency,
        )
        xml = await self._ibkr.get_fundamental_data(contract, req.report_type)
        response = FundamentalsResponse(
            symbol=req.symbol, report_type=req.report_type, xml_data=xml,
        )
        await self._fund_repo.upsert(response)
        return response

    async def get_earnings(self, req: EarningsRequest) -> EarningsResponse:
        """Return earnings data (CalendarReport), using the cache when available."""
        cached = await self._earn_repo.get(req.symbol)
        if cached:
            log.info("cache_hit_earnings", symbol=req.symbol)
            return EarningsResponse(
                symbol=req.symbol, xml_data=cached.xml_data,
                cached=True, fetched_at=cached.fetched_at,
            )

        contract = self._ibkr.make_contract(
            symbol=req.symbol, sec_type=req.sec_type.value,
            exchange=req.exchange, currency=req.currency,
        )
        xml = await self._ibkr.get_fundamental_data(contract, "CalendarReport")
        response = EarningsResponse(symbol=req.symbol, xml_data=xml)
        await self._earn_repo.upsert(response)
        return response
```


***

## `src/ibkr_mcp_service/sync/sync_manager.py`

```python
"""Background sync process – periodically refreshes cached data from IBKR."""

import asyncio
from datetime import datetime

import structlog

from ibkr_mcp_service.config import get_settings
from ibkr_mcp_service.db.base import get_session_factory
from ibkr_mcp_service.db.orm_models import OHLCVBarORM, FundamentalsORM, EarningsORM
from ibkr_mcp_service.models.domain import (
    QuoteRequest, FundamentalsRequest, EarningsRequest,
    BarSize, WhatToShow, SecType,
)
from ibkr_mcp_service.services.ibkr_client import get_ibkr_client
from ibkr_mcp_service.services.quote_service import QuoteService
from ibkr_mcp_service.services.fundamentals_service import FundamentalsService
from sqlalchemy import select

log = structlog.get_logger(__name__)


class SyncManager:
    """Discovers all symbols in the DB and refreshes their data periodically."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._running = False

    async def run_forever(self) -> None:
        """Entry point for the background sync loop."""
        self._running = True
        log.info("sync_manager_started", interval=self._settings.sync_interval_seconds)
        while self._running:
            try:
                await self._sync_all()
            except Exception:
                log.exception("sync_cycle_failed")
            await asyncio.sleep(self._settings.sync_interval_seconds)

    def stop(self) -> None:
        """Signal the sync loop to stop after the current cycle."""
        self._running = False

    async def _sync_all(self) -> None:
        """Run one full sync cycle over all known symbols."""
        log.info("sync_cycle_started")
        factory = get_session_factory()
        ibkr = get_ibkr_client()

        async with factory() as session:
            # Collect distinct symbols from ohlcv_bars
            result = await session.execute(
                select(
                    OHLCVBarORM.symbol,
                    OHLCVBarORM.sec_type,
                    OHLCVBarORM.currency,
                    OHLCVBarORM.bar_size,
                    OHLCVBarORM.what_to_show,
                    OHLCVBarORM.adjusted,
                ).distinct()
            )
            quote_keys = result.fetchall()

        for row in quote_keys:
            try:
                req = QuoteRequest(
                    symbol=row.symbol,
                    sec_type=SecType(row.sec_type),
                    currency=row.currency,
                    bar_size=BarSize(row.bar_size),
                    what_to_show=WhatToShow(row.what_to_show),
                    adjusted=bool(row.adjusted),
                    duration=f"{self._settings.sync_lookback_days} D",
                )
                async with factory() as session:
                    svc = QuoteService(session, ibkr)
                    # Force refresh by clearing cache flag
                    resp = await ibkr.get_historical_data(
                        contract=ibkr.make_contract(req.symbol, req.sec_type.value),
                        end_datetime="",
                        duration_str=req.duration,
                        bar_size_setting=req.bar_size.value,
                        what_to_show=req.what_to_show.value,
                        use_rth=req.use_rth,
                    )
                    log.info("sync_refreshed_quote", symbol=req.symbol, bars=len(resp))
            except Exception:
                log.exception("sync_failed_for_symbol", symbol=row.symbol)

        log.info("sync_cycle_completed", symbols_processed=len(quote_keys))
```


***

## `src/ibkr_mcp_service/tools/mcp_tools.py`

```python
"""MCP tool definitions – the public interface of the service."""

import json
from typing import Any

import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ibkr_mcp_service.db.base import get_session_factory
from ibkr_mcp_service.models.domain import (
    BarSize, EarningsRequest, FundamentalsRequest,
    QuoteRequest, SecType, WhatToShow,
)
from ibkr_mcp_service.services.fundamentals_service import FundamentalsService
from ibkr_mcp_service.services.ibkr_client import get_ibkr_client
from ibkr_mcp_service.services.quote_service import QuoteService

log = structlog.get_logger(__name__)

server = Server("ibkr-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Advertise available MCP tools to callers."""
    return [
        Tool(
            name="get_quotes",
            description=(
                "Fetch historical OHLCV bars for a symbol from IBKR. "
                "Results are persisted and served from cache on subsequent calls."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker, e.g. AAPL"},
                    "sec_type": {
                        "type": "string",
                        "enum": [e.value for e in SecType],
                        "default": "STK",
                    },
                    "exchange": {"type": "string", "default": "SMART"},
                    "currency": {"type": "string", "default": "USD"},
                    "duration": {
                        "type": "string",
                        "default": "1 Y",
                        "description": "IBKR duration string, e.g. '30 D', '6 M', '1 Y'",
                    },
                    "bar_size": {
                        "type": "string",
                        "enum": [e.value for e in BarSize],
                        "default": "1 day",
                    },
                    "what_to_show": {
                        "type": "string",
                        "enum": [e.value for e in WhatToShow],
                        "default": "TRADES",
                    },
                    "use_rth": {"type": "boolean", "default": True},
                    "adjusted": {"type": "boolean", "default": True},
                    "end_datetime": {
                        "type": "string",
                        "default": "",
                        "description": "End datetime; empty = now",
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="get_fundamentals",
            description=(
                "Retrieve IBKR fundamental data XML for a symbol. "
                "Cached in PostgreSQL after the first request."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "sec_type": {"type": "string", "default": "STK"},
                    "exchange": {"type": "string", "default": "SMART"},
                    "currency": {"type": "string", "default": "USD"},
                    "report_type": {
                        "type": "string",
                        "default": "ReportsFinSummary",
                        "enum": [
                            "ReportsFinSummary", "ReportSnapshot",
                            "ReportsOwnership", "ReportRatios",
                            "CalendarReport", "RESC",
                        ],
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="get_earnings",
            description=(
                "Retrieve IBKR earnings/calendar data for a symbol. "
                "Cached in PostgreSQL after the first request."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "sec_type": {"type": "string", "default": "STK"},
                    "exchange": {"type": "string", "default": "SMART"},
                    "currency": {"type": "string", "default": "USD"},
                },
                "required": ["symbol"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Route MCP tool calls to the appropriate service."""
    factory = get_session_factory()
    ibkr = get_ibkr_client()

    async with factory() as session:
        if name == "get_quotes":
            req = QuoteRequest(**arguments)
            svc = QuoteService(session, ibkr)
            result = await svc.get_quotes(req)
            payload = result.model_dump(mode="json")

        elif name == "get_fundamentals":
            req = FundamentalsRequest(**arguments)
            svc = FundamentalsService(session, ibkr)
            result = await svc.get_fundamentals(req)
            payload = result.model_dump(mode="json")

        elif name == "get_earnings":
            req = EarningsRequest(**arguments)
            svc = FundamentalsService(session, ibkr)
            result = await svc.get_earnings(req)
            payload = result.model_dump(mode="json")

        else:
            payload = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(payload, default=str, indent=2))]


async def run_mcp_server() -> None:
    """Start the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
```


***

## `src/ibkr_mcp_service/main.py`

```python
"""Application entry point – starts the MCP server and background sync."""

import asyncio

import structlog

from ibkr_mcp_service.logging_config import configure_logging
from ibkr_mcp_service.services.ibkr_client import get_ibkr_client
from ibkr_mcp_service.sync.sync_manager import SyncManager
from ibkr_mcp_service.tools.mcp_tools import run_mcp_server

log = structlog.get_logger(__name__)


async def _startup() -> None:
    """Connect to IBKR and start background sync before serving MCP requests."""
    client = get_ibkr_client()
    await client.connect()


async def _async_main() -> None:
    configure_logging()
    await _startup()

    sync_manager = SyncManager()
    sync_task = asyncio.create_task(sync_manager.run_forever())

    try:
        await run_mcp_server()
    finally:
        sync_manager.stop()
        sync_task.cancel()
        await get_ibkr_client().disconnect()


def main() -> None:
    """Synchronous entry point wired up by pyproject.toml."""
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
```


***

## `alembic.ini` (root)

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url = postgresql+psycopg2://ibkr:password@localhost:5432/ibkr_mcp

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```


***

## `alembic/env.py`

```python
"""Alembic migration environment – async-aware."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from ibkr_mcp_service.db.base import Base
from ibkr_mcp_service.db.orm_models import *  # noqa: F401,F403 – register all ORM models

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```


***

## `alembic/versions/0001_initial.py`

```python
"""Initial schema: ohlcv_bars, fundamentals, earnings.

Revision ID: 0001
Revises:
Create Date: 2026-05-15
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ohlcv_bars",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("sec_type", sa.String(10), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("bar_size", sa.String(20), nullable=False),
        sa.Column("what_to_show", sa.String(20), nullable=False),
        sa.Column("adjusted", sa.Integer, nullable=False, server_default="1"),
        sa.Column("bar_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float, nullable=False),
        sa.Column("high", sa.Float, nullable=False),
        sa.Column("low", sa.Float, nullable=False),
        sa.Column("close", sa.Float, nullable=False),
        sa.Column("volume", sa.Float, nullable=False),
        sa.Column("wap", sa.Float),
        sa.Column("bar_count", sa.Integer),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "symbol", "sec_type", "currency", "bar_size",
            "what_to_show", "adjusted", "bar_date",
            name="uq_ohlcv_bar",
        ),
    )
    op.create_index("ix_ohlcv_symbol_date", "ohlcv_bars", ["symbol", "bar_date"])

    op.create_table(
        "fundamentals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("sec_type", sa.String(10), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("xml_data", sa.Text, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", "report_type", name="uq_fundamentals"),
    )

    op.create_table(
        "earnings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("sec_type", sa.String(10), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("xml_data", sa.Text, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", name="uq_earnings_symbol"),
    )


def downgrade() -> None:
    op.drop_table("earnings")
    op.drop_table("fundamentals")
    op.drop_index("ix_ohlcv_symbol_date", table_name="ohlcv_bars")
    op.drop_table("ohlcv_bars")
```


***

## Tests

### `tests/unit/test_domain_models.py`

```python
"""Unit tests for Pydantic domain models."""

import pytest
from pydantic import ValidationError

from ibkr_mcp_service.models.domain import (
    BarSize, QuoteRequest, FundamentalsRequest, EarningsRequest, SecType, WhatToShow,
)


def test_quote_request_defaults():
    req = QuoteRequest(symbol="aapl")
    assert req.symbol == "AAPL"           # normalised to upper
    assert req.sec_type == SecType.STK
    assert req.bar_size == BarSize.D1
    assert req.what_to_show == WhatToShow.TRADES
    assert req.use_rth is True
    assert req.adjusted is True
    assert req.duration == "1 Y"
    assert req.end_datetime == ""


def test_quote_request_custom_values():
    req = QuoteRequest(
        symbol="eurusd",
        sec_type="CASH",
        exchange="IDEALPRO",
        currency="EUR",
        duration="30 D",
        bar_size="1 hour",
        what_to_show="MIDPOINT",
        use_rth=False,
        adjusted=False,
    )
    assert req.symbol == "EURUSD"
    assert req.sec_type == SecType.CASH
    assert req.bar_size == BarSize.H1
    assert req.use_rth is False


def test_quote_request_invalid_bar_size():
    with pytest.raises(ValidationError):
        QuoteRequest(symbol="AAPL", bar_size="99 years")


def test_fundamentals_request_defaults():
    req = FundamentalsRequest(symbol="msft")
    assert req.symbol == "MSFT"
    assert req.report_type == "ReportsFinSummary"


def test_earnings_request_normalises_symbol():
    req = EarningsRequest(symbol=" tsla ")
    assert req.symbol == "TSLA"
```


***

### `tests/unit/test_repository.py`

```python
"""Unit tests for repository layer using mocked AsyncSession."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ibkr_mcp_service.db.repository import QuoteRepository
from ibkr_mcp_service.models.domain import OHLCVBar, QuoteResponse


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def sample_response():
    return QuoteResponse(
        symbol="AAPL",
        sec_type="STK",
        currency="USD",
        bar_size="1 day",
        what_to_show="TRADES",
        adjusted=True,
        bars=[
            OHLCVBar(
                date=datetime(2025, 1, 2, tzinfo=timezone.utc),
                open=185.0, high=190.0, low=184.0, close=188.0, volume=50_000_000,
            )
        ],
    )


@pytest.mark.asyncio
async def test_upsert_bars_calls_execute(mock_session, sample_response):
    repo = QuoteRepository(mock_session)
    # Mock the execute result to have rowcount
    mock_result = MagicMock()
    mock_result.rowcount = 1
    mock_session.execute.return_value = mock_result

    with patch("ibkr_mcp_service.db.repository.insert") as mock_insert:
        mock_stmt = MagicMock()
        mock_stmt.on_conflict_do_update.return_value = mock_stmt
        mock_insert.return_value = mock_stmt

        count = await repo.upsert_bars(sample_response)

    mock_session.execute.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_bars_empty_returns_zero(mock_session):
    repo = QuoteRepository(mock_session)
    response = QuoteResponse(
        symbol="AAPL", sec_type="STK", currency="USD",
        bar_size="1 day", what_to_show="TRADES", adjusted=True, bars=[],
    )
    count = await repo.upsert_bars(response)
    assert count == 0
    mock_session.execute.assert_not_called()
```


***

### `tests/unit/test_quote_service.py`

```python
"""Unit tests for QuoteService cache-first logic."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ibkr_mcp_service.models.domain import (
    BarSize, OHLCVBar, QuoteRequest, QuoteResponse, SecType, WhatToShow,
)
from ibkr_mcp_service.services.quote_service import QuoteService


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_ibkr():
    return AsyncMock()


@pytest.fixture
def sample_bars():
    return [
        OHLCVBar(
            date=datetime(2025, 6, 1, tzinfo=timezone.utc),
            open=200.0, high=205.0, low=198.0, close=203.0, volume=1_000_000,
        )
    ]


@pytest.mark.asyncio
async def test_get_quotes_returns_cache_when_available(mock_session, mock_ibkr, sample_bars):
    """When the DB has bars, IBKR should NOT be called."""
    req = QuoteRequest(symbol="AAPL")

    with patch("ibkr_mcp_service.services.quote_service.QuoteRepository") as MockRepo:
        repo_instance = AsyncMock()
        repo_instance.get_bars.return_value = sample_bars
        MockRepo.return_value = repo_instance

        svc = QuoteService(mock_session, mock_ibkr)
        resp = await svc.get_quotes(req)

    assert resp.cached is True
    assert len(resp.bars) == 1
    mock_ibkr.get_historical_data.assert_not_called()


@pytest.mark.asyncio
async def test_get_quotes_fetches_from_ibkr_on_cache_miss(mock_session, mock_ibkr):
    """When the DB is empty, IBKR is called and results are persisted."""
    req = QuoteRequest(symbol="TSLA")

    # Simulate raw ib_async BarData-like object
    raw_bar = MagicMock()
    raw_bar.date = datetime(2025, 6, 1, tzinfo=timezone.utc)
    raw_bar.open = 250.0
    raw_bar.high = 260.0
    raw_bar.low = 248.0
    raw_bar.close = 255.0
    raw_bar.volume = 500_000.0
    raw_bar.wap = 253.0
    raw_bar.barCount = 1500

    mock_ibkr.get_historical_data = AsyncMock(return_value=[raw_bar])
    mock_ibkr.make_contract = MagicMock(return_value=MagicMock())

    with patch("ibkr_mcp_service.services.quote_service.QuoteRepository") as MockRepo:
        repo_instance = AsyncMock()
        repo_instance.get_bars.return_value = []   # cache miss
        repo_instance.upsert_bars = AsyncMock()
        MockRepo.return_value = repo_instance

        svc = QuoteService(mock_session, mock_ibkr)
        resp = await svc.get_quotes(req)

    assert resp.cached is False
    assert resp.symbol == "TSLA"
    assert len(resp.bars) == 1
    assert resp.bars[0].close == 255.0
    repo_instance.upsert_bars.assert_called_once()
```


***

### `tests/integration/test_db_integration.py`

```python
"""Integration tests for the repository layer against a real PostgreSQL instance.

Requires DATABASE_URL to be set (e.g. via docker-compose test service).
Skip automatically when the DB is unavailable.
"""

import os
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ibkr_mcp_service.db.base import Base
from ibkr_mcp_service.db.repository import QuoteRepository
from ibkr_mcp_service.models.domain import OHLCVBar, QuoteResponse

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://ibkr:password@localhost:5432/ibkr_mcp_test",
)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest.mark.asyncio
async def test_upsert_and_retrieve_bars(session):
    repo = QuoteRepository(session)
    response = QuoteResponse(
        symbol="INTC",
        sec_type="STK",
        currency="USD",
        bar_size="1 day",
        what_to_show="TRADES",
        adjusted=True,
        bars=[
            OHLCVBar(
                date=datetime(2025, 3, 10, tzinfo=timezone.utc),
                open=40.0, high=42.0, low=39.5, close=41.5, volume=8_000_000,
            ),
            OHLCVBar(
                date=datetime(2025, 3, 11, tzinfo=timezone.utc),
                open=41.5, high=43.0, low=41.0, close=42.8, volume=7_500_000,
            ),
        ],
    )
    await repo.upsert_bars(response)

    bars = await repo.get_bars(
        symbol="INTC", sec_type="STK", currency="USD",
        bar_size="1 day", what_to_show="TRADES", adjusted=True,
    )
    assert len(bars) == 2
    assert bars[0].close == 41.5
    assert bars[1].close == 42.8


@pytest.mark.asyncio
async def test_upsert_idempotent(session):
    """Running upsert twice must not create duplicate rows."""
    repo = QuoteRepository(session)
    response = QuoteResponse(
        symbol="NVDA", sec_type="STK", currency="USD",
        bar_size="1 day", what_to_show="TRADES", adjusted=True,
        bars=[
            OHLCVBar(
                date=datetime(2025, 4, 1, tzinfo=timezone.utc),
                open=800.0, high=820.0, low=795.0, close=815.0, volume=30_000_000,
            )
        ],
    )
    await repo.upsert_bars(response)
    await repo.upsert_bars(response)  # second upsert – must not raise

    bars = await repo.get_bars(
        symbol="NVDA", sec_type="STK", currency="USD",
        bar_size="1 day", what_to_show="TRADES", adjusted=True,
    )
    assert len(bars) == 1
```


***

## `docker-compose.yml`

```yaml
version: "3.9"

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
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ibkr"]
      interval: 5s
      timeout: 5s
      retries: 10

  ibkr-mcp:
    build:
      context: .
      dockerfile: Dockerfile
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql+asyncpg://ibkr:password@postgres:5432/ibkr_mcp
      IBKR_HOST: ${IBKR_HOST:-host.docker.internal}
      IBKR_PORT: ${IBKR_PORT:-7497}
      IBKR_CLIENT_ID: 1
      LOG_LEVEL: INFO
      LOG_FORMAT: json
    stdin_open: true  # MCP uses stdio transport
    tty: false
    extra_hosts:
      - "host.docker.internal:host-gateway"

volumes:
  pgdata:
```


***

## `Dockerfile`

```dockerfile
FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency manifest
COPY pyproject.toml .
COPY README.md .

# Install dependencies (no dev extras)
RUN uv venv .venv && \
    uv pip install --no-cache --python .venv/bin/python ".[standard]" || \
    uv pip install --no-cache --python .venv/bin/python .

# Copy source
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

# Runtime image
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app/src"

# Run Alembic migrations then start the MCP server
ENTRYPOINT ["sh", "-c", "alembic upgrade head && ibkr-mcp"]
```


***

## `README.md`

````markdown
# IBKR MCP Service

An **MCP (Model Context Protocol) server** that exposes Interactive Brokers market data tools
via `ib_async`, with PostgreSQL persistence and background sync.

## Tools

| Tool | Description |
|---|---|
| `get_quotes` | Historical OHLCV bars — symbol, duration, bar size, adjusted flag |
| `get_fundamentals` | Financial summary / ratios XML from IBKR |
| `get_earnings` | Earnings calendar report XML from IBKR |

All results are cached in PostgreSQL and returned from cache on subsequent calls.
A background sync process refreshes all cached symbols on a configurable interval.

## Quick Start

### 1 — Prerequisites

- IB Gateway or TWS running with API enabled on port `7497` (TWS) / `4001` (Gateway)
- Docker + Docker Compose OR Python 3.11+ with [uv](https://github.com/astral-sh/uv)

### 2 — Docker (recommended)

```bash
cp .env.example .env          # edit IBKR_HOST / PORT if needed
docker compose up -d postgres
docker compose up ibkr-mcp
```

### 3 — Local development

```bash
uv venv
uv pip install -e ".[dev]"
cp .env.example .env

# Start Postgres separately, then:
alembic upgrade head
ibkr-mcp
```

### 4 — Run tests

```bash
# Unit only (no DB needed)
pytest tests/unit -v

# Integration (needs Postgres)
DATABASE_URL=postgresql+asyncpg://ibkr:password@localhost:5432/ibkr_mcp_test \
  pytest tests/integration -v

# Full suite with coverage
pytest --cov=src --cov-report=html
```

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

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `IBKR_HOST` | `127.0.0.1` | TWS/Gateway host |
| `IBKR_PORT` | `7497` | 7497=TWS, 4001=Gateway |
| `IBKR_CLIENT_ID` | `1` | Unique connection ID |
| `IBKR_TIMEOUT` | `30` | Connect timeout (s) |
| `DATABASE_URL` | `postgresql+asyncpg://ibkr:password@localhost:5432/ibkr_mcp` | Async PG DSN |
| `SYNC_INTERVAL_SECONDS` | `300` | Background sync cadence |
| `SYNC_LOOKBACK_DAYS` | `365` | Historical window on refresh |
| `LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING` |
| `LOG_FORMAT` | `json` | `json` or `console` |
````


***

## Architecture Overview

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
    │   (periodic refresh loop)    │
    └──────────────────────────────┘
```


***

## Key Design Decisions

**Cache-first with async upsert** — every live IBKR response is immediately stored using PostgreSQL `INSERT ... ON CONFLICT DO UPDATE`, ensuring idempotent writes and no duplicate rows even when the sync loop and an MCP call race.

**Single `ib_async` connection with `asyncio.Lock`** — `ib_async` multiplexes over one TCP socket to TWS/Gateway; the lock prevents concurrent `reqHistoricalData` calls from interleaving responses.

**`tenacity` retry on connect** — IBKR's gateway can take a few seconds to accept connections; three attempts with exponential back-off cover transient failures without blocking the MCP server indefinitely.

**Alembic for migrations** — schema changes are version-controlled and applied automatically in the Docker `ENTRYPOINT` before the server starts, so the DB is always in sync with the code.

**`uv` as package manager** — `uv venv` + `uv pip install` replaces pip/poetry for significantly faster dependency resolution and lock-file generation.

