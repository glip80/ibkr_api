"""Unit tests for SyncService background sync logic."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ibkr_mcp_service.services.sync_service import SyncService


@pytest.mark.asyncio
async def test_sync_all_ohlcv_updated():
    """QuoteService.get_quotes is called for each OHLCV key with force_refresh."""
    sm = SyncService()

    ohlcv_row = MagicMock()
    ohlcv_row.symbol = "AAPL"
    ohlcv_row.sec_type = "STK"
    ohlcv_row.currency = "USD"
    ohlcv_row.bar_size = "1 day"
    ohlcv_row.what_to_show = "TRADES"
    ohlcv_row.adjusted = True

    sm._get_ohlcv_keys = AsyncMock(return_value=[ohlcv_row])
    sm._get_fundamentals_keys = AsyncMock(return_value=[])
    sm._get_earnings_symbols = AsyncMock(return_value=[])

    with (
        patch("ibkr_mcp_service.services.sync_service.QuoteService") as MockQS,
        patch("ibkr_mcp_service.services.sync_service.get_session_factory") as MockFactory,
        patch("ibkr_mcp_service.services.sync_service.get_ibkr_client"),
    ):
        mock_qs_instance = AsyncMock()
        MockQS.return_value = mock_qs_instance
        mock_session = AsyncMock()
        MockFactory.return_value = MagicMock(return_value=mock_session)

        await sm._sync_all()

    mock_qs_instance.get_quotes.assert_called_once()
    _call_args, call_kwargs = mock_qs_instance.get_quotes.call_args
    assert call_kwargs.get("force_refresh") is True


@pytest.mark.asyncio
async def test_sync_all_fundamentals_updated():
    """FundamentalsService.get_fundamentals is called for each fund key."""
    sm = SyncService()

    fund_row = MagicMock()
    fund_row.symbol = "MSFT"
    fund_row.sec_type = "STK"
    fund_row.currency = "USD"
    fund_row.report_type = "ReportsFinSummary"

    sm._get_ohlcv_keys = AsyncMock(return_value=[])
    sm._get_fundamentals_keys = AsyncMock(return_value=[fund_row])
    sm._get_earnings_symbols = AsyncMock(return_value=[])

    with (
        patch(
            "ibkr_mcp_service.services.sync_service.FundamentalsService"
        ) as MockFS,
        patch("ibkr_mcp_service.services.sync_service.get_session_factory") as MockFactory,
        patch("ibkr_mcp_service.services.sync_service.get_ibkr_client"),
    ):
        mock_fs_instance = AsyncMock()
        MockFS.return_value = mock_fs_instance
        mock_session = AsyncMock()
        MockFactory.return_value = MagicMock(return_value=mock_session)

        await sm._sync_all()

    mock_fs_instance.get_fundamentals.assert_called_once()
    _call_args, call_kwargs = mock_fs_instance.get_fundamentals.call_args
    assert call_kwargs.get("force_refresh") is True


@pytest.mark.asyncio
async def test_sync_all_earnings_updated():
    """FundamentalsService.get_earnings is called for each earnings symbol."""
    sm = SyncService()

    earn_row = MagicMock()
    earn_row.symbol = "TSLA"
    earn_row.sec_type = "STK"
    earn_row.currency = "USD"

    sm._get_ohlcv_keys = AsyncMock(return_value=[])
    sm._get_fundamentals_keys = AsyncMock(return_value=[])
    sm._get_earnings_symbols = AsyncMock(return_value=[earn_row])

    with (
        patch(
            "ibkr_mcp_service.services.sync_service.EarningsService"
        ) as MockES,
        patch("ibkr_mcp_service.services.sync_service.get_session_factory") as MockFactory,
        patch("ibkr_mcp_service.services.sync_service.get_ibkr_client"),
    ):
        mock_es_instance = AsyncMock()
        MockES.return_value = mock_es_instance
        mock_session = AsyncMock()
        MockFactory.return_value = MagicMock(return_value=mock_session)

        await sm._sync_all()

    mock_es_instance.get_earnings.assert_called_once()
    _call_args, call_kwargs = mock_es_instance.get_earnings.call_args
    assert call_kwargs.get("force_refresh") is True


@pytest.mark.asyncio
async def test_sync_all_empty_tables():
    """When all tables are empty, no services should be called."""
    sm = SyncService()
    sm._get_ohlcv_keys = AsyncMock(return_value=[])
    sm._get_fundamentals_keys = AsyncMock(return_value=[])
    sm._get_earnings_symbols = AsyncMock(return_value=[])

    with (
        patch("ibkr_mcp_service.services.sync_service.QuoteService") as MockQS,
        patch("ibkr_mcp_service.services.sync_service.FundamentalsService") as MockFS,
        patch("ibkr_mcp_service.services.sync_service.EarningsService") as MockES,
        patch("ibkr_mcp_service.services.sync_service.get_session_factory") as MockFactory,
        patch("ibkr_mcp_service.services.sync_service.get_ibkr_client"),
    ):
        mock_session = AsyncMock()
        MockFactory.return_value = MagicMock(return_value=mock_session)

        await sm._sync_all()

    MockQS.assert_not_called()
    MockFS.assert_not_called()
    MockES.assert_not_called()


def test_stop_sets_flag():
    """stop() sets _running to False."""
    sm = SyncService()
    assert sm._running is False
    sm._running = True
    sm.stop()
    assert sm._running is False


@pytest.mark.asyncio
async def test_run_forever_loops_until_stopped():
    """run_forever loops calling _sync_all until stop() is called."""
    sm = SyncService()
    sm._sync_all = AsyncMock()
    sm._running = True

    async def _run():
        await sm.run_forever()

    task = asyncio.create_task(_run())
    await asyncio.sleep(0.05)
    sm.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert sm._sync_all.call_count >= 1
