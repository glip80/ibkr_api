"""Unit tests for IBKRClient connection and data-fetching logic."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ibkr_mcp_service.ibkr.client import IBKRClient


@pytest.fixture
def ibkr_client():
    """Return an IBKRClient whose _ib attribute is fully mocked."""
    client = IBKRClient()
    client._ib = MagicMock()
    client._ib.isConnected.return_value = False
    client._ib.connectAsync = AsyncMock()
    client._ib.disconnect = MagicMock()
    client._ib.reqHistoricalDataAsync = AsyncMock()
    client._ib.reqFundamentalDataAsync = AsyncMock()
    client._lock = MagicMock()
    client._lock.__aenter__ = AsyncMock()
    client._lock.__aexit__ = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_connect_when_disconnected_calls_ib_connect(ibkr_client):
    """When not connected, connectAsync should be called."""
    ibkr_client._ib.isConnected.return_value = False
    await ibkr_client.connect()
    assert ibkr_client._ib.connectAsync.called


@pytest.mark.asyncio
async def test_connect_when_already_connected_skips(ibkr_client):
    """When already connected, connectAsync should NOT be called."""
    ibkr_client._ib.isConnected.return_value = True
    await ibkr_client.connect()
    ibkr_client._ib.connectAsync.assert_not_called()


@pytest.mark.asyncio
async def test_disconnect_when_connected_calls_disconnect(ibkr_client):
    """When connected, ib.disconnect should be called."""
    ibkr_client._ib.isConnected.return_value = True
    await ibkr_client.disconnect()
    ibkr_client._ib.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_disconnect_when_disconnected_skips(ibkr_client):
    """When not connected, ib.disconnect should NOT be called."""
    ibkr_client._ib.isConnected.return_value = False
    await ibkr_client.disconnect()
    ibkr_client._ib.disconnect.assert_not_called()


def test_make_contract_creates_valid_contract(ibkr_client):
    """make_contract should return a Contract with the correct attributes."""
    contract = ibkr_client.make_contract(
        symbol="AAPL", sec_type="STK", exchange="SMART", currency="USD",
    )
    assert contract.symbol == "AAPL"
    assert contract.secType == "STK"
    assert contract.exchange == "SMART"
    assert contract.currency == "USD"


def test_make_contract_applies_defaults(ibkr_client):
    """make_contract should use defaults when only symbol is given."""
    contract = ibkr_client.make_contract(symbol="MSFT")
    assert contract.symbol == "MSFT"
    assert contract.secType == "STK"
    assert contract.exchange == "SMART"
    assert contract.currency == "USD"


@pytest.mark.asyncio
async def test_get_historical_data_returns_bars():
    from ibkr_mcp_service.ibkr.quotes import get_historical_data

    client = MagicMock()
    client.lock = MagicMock()
    client.lock.__aenter__ = AsyncMock()
    client.lock.__aexit__ = AsyncMock()
    expected_bars = MagicMock()
    client._ib = MagicMock()
    client._ib.reqHistoricalDataAsync = AsyncMock(return_value=expected_bars)

    contract = MagicMock()
    bars = await get_historical_data(
        client,
        contract=contract,
        end_datetime="",
        duration_str="1 Y",
        bar_size_setting="1 day",
        what_to_show="TRADES",
        use_rth=True,
    )

    assert bars is expected_bars
    client._ib.reqHistoricalDataAsync.assert_called_once()


@pytest.mark.asyncio
async def test_get_fundamental_data_returns_xml():
    from ibkr_mcp_service.ibkr.fundamentals import get_fundamental_data

    client = MagicMock()
    client.lock = MagicMock()
    client.lock.__aenter__ = AsyncMock()
    client.lock.__aexit__ = AsyncMock()
    expected_xml = "<xml>financials</xml>"
    client._ib = MagicMock()
    client._ib.reqFundamentalDataAsync = AsyncMock(return_value=expected_xml)

    contract = MagicMock()
    xml = await get_fundamental_data(
        client, contract=contract, report_type="ReportsFinSummary",
    )

    assert xml == expected_xml
    client._ib.reqFundamentalDataAsync.assert_called_once()
