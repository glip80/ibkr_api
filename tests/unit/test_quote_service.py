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