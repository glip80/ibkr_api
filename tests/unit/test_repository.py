"""Unit tests for repository layer using mocked AsyncSession."""

from datetime import UTC, datetime
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
                date=datetime(2025, 1, 2, tzinfo=UTC),
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