"""Unit tests for FundamentalsService cache-first logic."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ibkr_mcp_service.models.domain import (
    EarningsRequest,
    FundamentalsRequest,
)
from ibkr_mcp_service.services.fundamentals_service import FundamentalsService


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_ibkr():
    client = AsyncMock()
    client.make_contract = MagicMock(return_value=MagicMock())
    client.get_fundamental_data = AsyncMock(return_value="<xml>response</xml>")
    return client


@pytest.fixture
def cached_fund_orm():
    obj = MagicMock()
    obj.xml_data = "<xml>cached</xml>"
    obj.fetched_at = datetime(2025, 1, 1, tzinfo=UTC)
    return obj


@pytest.fixture
def cached_earn_orm():
    obj = MagicMock()
    obj.xml_data = "<xml>earnings_cached</xml>"
    obj.fetched_at = datetime(2025, 1, 1, tzinfo=UTC)
    return obj


@pytest.mark.asyncio
async def test_get_fundamentals_returns_cache_when_available(
    mock_session, mock_ibkr, cached_fund_orm
):
    """When the DB has fundamentals, IBKR should NOT be called."""
    req = FundamentalsRequest(symbol="AAPL")

    with patch(
        "ibkr_mcp_service.services.fundamentals_service.FundamentalsRepository"
    ) as MockRepo:
        repo_instance = AsyncMock()
        repo_instance.get.return_value = cached_fund_orm
        MockRepo.return_value = repo_instance

        svc = FundamentalsService(mock_session, mock_ibkr)
        resp = await svc.get_fundamentals(req)

    assert resp.cached is True
    assert "cached" in resp.xml_data
    mock_ibkr.get_fundamental_data.assert_not_called()
    repo_instance.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_get_fundamentals_fetches_from_ibkr_on_cache_miss(
    mock_session, mock_ibkr,
):
    """When the DB is empty, IBKR is called and results are persisted."""
    req = FundamentalsRequest(symbol="MSFT")

    with patch(
        "ibkr_mcp_service.services.fundamentals_service.FundamentalsRepository"
    ) as MockRepo:
        repo_instance = AsyncMock()
        repo_instance.get.return_value = None
        MockRepo.return_value = repo_instance

        svc = FundamentalsService(mock_session, mock_ibkr)
        resp = await svc.get_fundamentals(req)

    assert resp.cached is False
    assert resp.xml_data == "<xml>response</xml>"
    mock_ibkr.get_fundamental_data.assert_called_once()
    repo_instance.upsert.assert_called_once_with(resp)


@pytest.mark.asyncio
async def test_get_fundamentals_force_refresh_skips_cache(
    mock_session, mock_ibkr, cached_fund_orm,
):
    """When force_refresh=True, IBKR is called even if cache exists."""
    req = FundamentalsRequest(symbol="GOOGL")

    with patch(
        "ibkr_mcp_service.services.fundamentals_service.FundamentalsRepository"
    ) as MockRepo:
        repo_instance = AsyncMock()
        repo_instance.get.return_value = cached_fund_orm
        MockRepo.return_value = repo_instance

        svc = FundamentalsService(mock_session, mock_ibkr)
        resp = await svc.get_fundamentals(req, force_refresh=True)

    assert resp.cached is False
    assert resp.xml_data == "<xml>response</xml>"
    mock_ibkr.get_fundamental_data.assert_called_once()
    repo_instance.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_get_earnings_returns_cache_when_available(
    mock_session, mock_ibkr, cached_earn_orm,
):
    """When the DB has cached earnings, IBKR should NOT be called."""
    req = EarningsRequest(symbol="AAPL")

    with patch(
        "ibkr_mcp_service.services.fundamentals_service.EarningsRepository"
    ) as MockRepo:
        repo_instance = AsyncMock()
        repo_instance.get.return_value = cached_earn_orm
        MockRepo.return_value = repo_instance

        svc = FundamentalsService(mock_session, mock_ibkr)
        resp = await svc.get_earnings(req)

    assert resp.cached is True
    assert "earnings_cached" in resp.xml_data
    mock_ibkr.get_fundamental_data.assert_not_called()
    repo_instance.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_get_earnings_fetches_from_ibkr_on_cache_miss(
    mock_session, mock_ibkr,
):
    """When the DB is empty, IBKR is called and results are persisted."""
    req = EarningsRequest(symbol="TSLA")

    with patch(
        "ibkr_mcp_service.services.fundamentals_service.EarningsRepository"
    ) as MockRepo:
        repo_instance = AsyncMock()
        repo_instance.get.return_value = None
        MockRepo.return_value = repo_instance

        svc = FundamentalsService(mock_session, mock_ibkr)
        resp = await svc.get_earnings(req)

    assert resp.cached is False
    assert resp.xml_data == "<xml>response</xml>"
    mock_ibkr.get_fundamental_data.assert_called_once()
    repo_instance.upsert.assert_called_once_with(resp)


@pytest.mark.asyncio
async def test_get_earnings_force_refresh_skips_cache(
    mock_session, mock_ibkr, cached_earn_orm,
):
    """When force_refresh=True, IBKR is called even if cache exists."""
    req = EarningsRequest(symbol="NVDA")

    with patch(
        "ibkr_mcp_service.services.fundamentals_service.EarningsRepository"
    ) as MockRepo:
        repo_instance = AsyncMock()
        repo_instance.get.return_value = cached_earn_orm
        MockRepo.return_value = repo_instance

        svc = FundamentalsService(mock_session, mock_ibkr)
        resp = await svc.get_earnings(req, force_refresh=True)

    assert resp.cached is False
    mock_ibkr.get_fundamental_data.assert_called_once()
    repo_instance.upsert.assert_called_once()
