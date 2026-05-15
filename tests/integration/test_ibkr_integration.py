"""
Integration tests for the full stack (IBKRClient + PersistenceStore + server).

These tests require a running TWS / IB Gateway instance.
Set IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID in environment, then run:

    pytest tests/integration/ -v --run-integration

The ``--run-integration`` flag is checked by the custom pytest marker below.
By default these tests are **skipped** so CI doesn't break without a TWS session.
"""

import os
from pathlib import Path

import pytest
import pytest_asyncio

from ibkr_mcp.config import settings
from ibkr_mcp.ibkr_client import IBKRClient
from ibkr_mcp.persistence import PersistenceStore
from ibkr_mcp.server import _dispatch

# ── marker registration (conftest alternative) ───────────────────────────────

INTEGRATION_MARKER = "integration"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", f"{INTEGRATION_MARKER}: mark test as requiring live IBKR")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip integration tests unless --run-integration is passed."""
    if config.getoption("--run-integration", default=False):
        return
    skip = pytest.mark.skip(reason="Pass --run-integration to execute")
    for item in items:
        if INTEGRATION_MARKER in item.keywords:
            item.add_marker(skip)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--run-integration", action="store_true", default=False)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def live_client() -> IBKRClient:
    """Connect to a live TWS / IB Gateway."""
    client = IBKRClient(
        host=os.environ.get("IBKR_HOST", settings.ibkr_host),
        port=int(os.environ.get("IBKR_PORT", settings.ibkr_port)),
        client_id=int(os.environ.get("IBKR_CLIENT_ID", settings.ibkr_client_id)),
    )
    await client.connect()
    yield client
    await client.disconnect()


@pytest_asyncio.fixture
async def live_store(tmp_path: Path) -> PersistenceStore:
    s = PersistenceStore(db_path=tmp_path / "integration.db")
    await s.init()
    return s


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_get_historical_bars_aapl(live_client: IBKRClient) -> None:
    """Smoke test: fetch 5 days of daily bars for AAPL."""
    bars = await live_client.get_historical_bars(
        "AAPL", duration="5 D", bar_size="1 day", what_to_show="ADJUSTED_LAST"
    )
    assert len(bars) > 0
    first = bars[0]
    assert "date" in first
    assert "close" in first
    assert first["close"] > 0


@pytest.mark.integration
async def test_get_fundamentals_aapl(live_client: IBKRClient) -> None:
    """Smoke test: fetch financial summary XML for AAPL."""
    xml = await live_client.get_fundamentals("AAPL", report_type="ReportsFinSummary")
    assert xml
    assert "AAPL" in xml or "<" in xml  # Valid XML response


@pytest.mark.integration
async def test_get_earnings_aapl(live_client: IBKRClient) -> None:
    """Smoke test: fetch earnings RESC XML for AAPL."""
    xml = await live_client.get_earnings("AAPL")
    assert xml
    assert len(xml) > 100  # Non-trivial XML response


@pytest.mark.integration
async def test_full_stack_quotes(live_client: IBKRClient, live_store: PersistenceStore) -> None:
    """End-to-end: tool dispatcher fetches from IBKR and persists to SQLite."""
    bars = await _dispatch(
        "get_quotes",
        {"symbol": "AAPL", "duration": "5 D", "bar_size": "1 day"},
        live_client,
        live_store,
        None,
    )
    assert len(bars) > 0

    # Second call should hit cache
    from unittest.mock import AsyncMock, patch
    with patch.object(live_client, "get_historical_bars", new_callable=AsyncMock) as mock_fn:
        cached_bars = await _dispatch(
            "get_quotes",
            {"symbol": "AAPL", "duration": "5 D", "bar_size": "1 day"},
            live_client,
            live_store,
            None,
        )
        mock_fn.assert_not_called()
    assert len(cached_bars) == len(bars)


@pytest.mark.integration
async def test_trigger_sync_all(live_client: IBKRClient, live_store: PersistenceStore) -> None:
    """Trigger sync and verify data persisted for all data types."""
    result = await _dispatch(
        "trigger_sync",
        {"symbol": "AAPL", "data_type": "all"},
        live_client,
        live_store,
        None,
    )
    assert result.get("quotes") == "ok"
    assert result.get("fundamentals") == "ok"
    assert result.get("earnings") == "ok"
