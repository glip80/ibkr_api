"""Unit tests for PersistenceStore.

Uses an in-memory SQLite database (via :data:`DB_PATH=':memory:'` ) so
tests are fast and leave no side-effects.

Note: aiosqlite does not support ':memory:' across multiple connections;
we use a temp file instead.
"""

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio

from ibkr_mcp.persistence import PersistenceStore


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Return a temporary SQLite database path."""
    return tmp_path / "test.db"


@pytest_asyncio.fixture
async def store(tmp_db: Path) -> PersistenceStore:
    """Return an initialised PersistenceStore backed by a temp file."""
    s = PersistenceStore(db_path=tmp_db, quotes_ttl_hours=1, fundamentals_ttl_hours=24)
    await s.init()
    return s


_SAMPLE_BARS = [
    {"date": "2024-01-02", "open": 185.0, "high": 187.0, "low": 184.0,
     "close": 186.0, "volume": 1_000_000, "average": 185.5, "bar_count": 500},
    {"date": "2024-01-03", "open": 186.0, "high": 188.0, "low": 185.5,
     "close": 187.5, "volume": 900_000, "average": 186.8, "bar_count": 450},
]


class TestQuotes:
    async def test_upsert_and_get(self, store: PersistenceStore) -> None:
        await store.upsert_quotes("AAPL", "1 day", "ADJUSTED_LAST", _SAMPLE_BARS)
        bars, is_stale = await store.get_quotes("AAPL", "1 day", "ADJUSTED_LAST")
        assert len(bars) == 2
        assert not is_stale

    async def test_empty_returns_stale(self, store: PersistenceStore) -> None:
        bars, is_stale = await store.get_quotes("AAPL", "1 day", "ADJUSTED_LAST")
        assert bars == []
        assert is_stale

    async def test_symbol_case_insensitive(self, store: PersistenceStore) -> None:
        await store.upsert_quotes("aapl", "1 day", "ADJUSTED_LAST", _SAMPLE_BARS)
        bars, _ = await store.get_quotes("AAPL", "1 day", "ADJUSTED_LAST")
        assert len(bars) == 2

    async def test_date_filter(self, store: PersistenceStore) -> None:
        await store.upsert_quotes("AAPL", "1 day", "ADJUSTED_LAST", _SAMPLE_BARS)
        bars, _ = await store.get_quotes(
            "AAPL", "1 day", "ADJUSTED_LAST",
            start_date="2024-01-03", end_date="2024-01-03",
        )
        assert len(bars) == 1
        assert bars[0]["date"] == "2024-01-03"

    async def test_upsert_is_idempotent(self, store: PersistenceStore) -> None:
        await store.upsert_quotes("AAPL", "1 day", "ADJUSTED_LAST", _SAMPLE_BARS)
        await store.upsert_quotes("AAPL", "1 day", "ADJUSTED_LAST", _SAMPLE_BARS)
        bars, _ = await store.get_quotes("AAPL", "1 day", "ADJUSTED_LAST")
        assert len(bars) == 2  # No duplicates


class TestFundamentals:
    async def test_upsert_and_get(self, store: PersistenceStore) -> None:
        xml = "<ReportsFinSummary><symbol>AAPL</symbol></ReportsFinSummary>"
        await store.upsert_fundamentals("AAPL", "ReportsFinSummary", xml)
        result, is_stale = await store.get_fundamentals("AAPL", "ReportsFinSummary")
        assert result == xml
        assert not is_stale

    async def test_missing_returns_stale(self, store: PersistenceStore) -> None:
        result, is_stale = await store.get_fundamentals("AAPL", "ReportsFinSummary")
        assert result is None
        assert is_stale

    async def test_replace_on_upsert(self, store: PersistenceStore) -> None:
        await store.upsert_fundamentals("AAPL", "ReportsFinSummary", "<old/>")
        await store.upsert_fundamentals("AAPL", "ReportsFinSummary", "<new/>")
        result, _ = await store.get_fundamentals("AAPL", "ReportsFinSummary")
        assert result == "<new/>"


class TestEarnings:
    async def test_upsert_and_get(self, store: PersistenceStore) -> None:
        xml = "<RESC><symbol>AAPL</symbol></RESC>"
        await store.upsert_earnings("AAPL", xml)
        result, is_stale = await store.get_earnings("AAPL")
        assert result == xml
        assert not is_stale

    async def test_missing_returns_stale(self, store: PersistenceStore) -> None:
        result, is_stale = await store.get_earnings("AAPL")
        assert result is None
        assert is_stale


class TestSyncLog:
    async def test_log_and_retrieve(self, store: PersistenceStore) -> None:
        from ibkr_mcp.persistence import _utcnow
        started = _utcnow()
        await store.log_sync("AAPL", "quotes", "ok", None, started)
        logs = await store.get_sync_log(limit=10)
        assert len(logs) == 1
        assert logs[0]["symbol"] == "AAPL"
        assert logs[0]["status"] == "ok"

    async def test_limit_respected(self, store: PersistenceStore) -> None:
        from ibkr_mcp.persistence import _utcnow
        for i in range(5):
            await store.log_sync("AAPL", "quotes", "ok", None, _utcnow())
        logs = await store.get_sync_log(limit=3)
        assert len(logs) == 3
