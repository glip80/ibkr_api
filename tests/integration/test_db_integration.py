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