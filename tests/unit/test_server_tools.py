"""
Unit tests for the MCP server tool dispatcher.

The IBKR client is fully mocked so no real TWS connection is needed.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from ibkr_mcp.ibkr_client import IBKRClient
from ibkr_mcp.persistence import PersistenceStore
from ibkr_mcp.server import _dispatch

_BARS = [
    {"date": "2024-01-02", "open": 185.0, "high": 187.0, "low": 184.0,
     "close": 186.0, "volume": 1_000_000, "average": 185.5, "bar_count": 500},
]
_XML_FUNDAMENTALS = "<ReportsFinSummary/>"
_XML_EARNINGS = "<RESC/>"


@pytest.fixture
def mock_client() -> IBKRClient:
    """Return a mocked IBKRClient."""
    client = AsyncMock(spec=IBKRClient)
    client.connect = AsyncMock()
    client.get_historical_bars = AsyncMock(return_value=_BARS)
    client.get_fundamentals = AsyncMock(return_value=_XML_FUNDAMENTALS)
    client.get_earnings = AsyncMock(return_value=_XML_EARNINGS)
    return client


@pytest_asyncio.fixture
async def store(tmp_path: Path) -> PersistenceStore:
    s = PersistenceStore(db_path=tmp_path / "test.db", quotes_ttl_hours=1)
    await s.init()
    return s


class TestGetQuotesTool:
    async def test_cache_miss_fetches_ibkr(self, mock_client, store):
        result = await _dispatch("get_quotes", {"symbol": "AAPL"}, mock_client, store, None)
        mock_client.get_historical_bars.assert_called_once()
        assert len(result) == 1

    async def test_cache_hit_skips_ibkr(self, mock_client, store):
        # Pre-populate cache
        await store.upsert_quotes("AAPL", "1 day", "ADJUSTED_LAST", _BARS)
        result = await _dispatch("get_quotes", {"symbol": "AAPL"}, mock_client, store, None)
        mock_client.get_historical_bars.assert_not_called()
        assert len(result) == 1

    async def test_defaults_applied(self, mock_client, store):
        await _dispatch("get_quotes", {"symbol": "TSLA"}, mock_client, store, None)
        call_kwargs = mock_client.get_historical_bars.call_args
        assert call_kwargs.kwargs.get("bar_size", "1 day") == "1 day"
        assert call_kwargs.kwargs.get("what_to_show", "ADJUSTED_LAST") == "ADJUSTED_LAST"

    async def test_custom_bar_size(self, mock_client, store):
        await _dispatch(
            "get_quotes",
            {"symbol": "AAPL", "bar_size": "1 hour", "what_to_show": "TRADES"},
            mock_client, store, None,
        )
        mock_client.get_historical_bars.assert_called_once()
        _, kwargs = mock_client.get_historical_bars.call_args
        assert kwargs["bar_size"] == "1 hour"


class TestGetFundamentalsTool:
    async def test_cache_miss_fetches_ibkr(self, mock_client, store):
        result = await _dispatch("get_fundamentals", {"symbol": "AAPL"}, mock_client, store, None)
        mock_client.get_fundamentals.assert_called_once()
        assert result == _XML_FUNDAMENTALS

    async def test_cache_hit_skips_ibkr(self, mock_client, store):
        await store.upsert_fundamentals("AAPL", "ReportsFinSummary", _XML_FUNDAMENTALS)
        result = await _dispatch("get_fundamentals", {"symbol": "AAPL"}, mock_client, store, None)
        mock_client.get_fundamentals.assert_not_called()
        assert result == _XML_FUNDAMENTALS

    async def test_default_report_type(self, mock_client, store):
        await _dispatch("get_fundamentals", {"symbol": "AAPL"}, mock_client, store, None)
        _, kwargs = mock_client.get_fundamentals.call_args
        assert kwargs.get("report_type", "ReportsFinSummary") == "ReportsFinSummary"


class TestGetEarningsTool:
    async def test_cache_miss_fetches_ibkr(self, mock_client, store):
        result = await _dispatch("get_earnings", {"symbol": "AAPL"}, mock_client, store, None)
        mock_client.get_earnings.assert_called_once()
        assert result == _XML_EARNINGS

    async def test_cache_hit_skips_ibkr(self, mock_client, store):
        await store.upsert_earnings("AAPL", _XML_EARNINGS)
        result = await _dispatch("get_earnings", {"symbol": "AAPL"}, mock_client, store, None)
        mock_client.get_earnings.assert_not_called()


class TestGetSyncLog:
    async def test_returns_log_entries(self, mock_client, store):
        from ibkr_mcp.persistence import _utcnow
        await store.log_sync("AAPL", "quotes", "ok", None, _utcnow())
        result = await _dispatch("get_sync_log", {"limit": 10}, mock_client, store, None)
        assert len(result) == 1

    async def test_default_limit_applied(self, mock_client, store):
        result = await _dispatch("get_sync_log", {}, mock_client, store, None)
        assert isinstance(result, list)


class TestUnknownTool:
    async def test_raises_value_error(self, mock_client, store):
        with pytest.raises(ValueError, match="Unknown tool"):
            await _dispatch("nonexistent_tool", {}, mock_client, store, None)
