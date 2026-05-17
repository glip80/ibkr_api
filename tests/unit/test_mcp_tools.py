import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import TextContent

from ibkr_mcp_service.mcp.server import call_tool, list_tools
from ibkr_mcp_service.mcp.tools.get_earnings import handle_get_earnings, handle_sync_symbol
from ibkr_mcp_service.mcp.tools.get_fundamental import handle as handle_fundamentals
from ibkr_mcp_service.mcp.tools.get_quote import handle as handle_quote


@pytest.fixture
def mock_ibkr():
    return MagicMock()


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.__aenter__ = AsyncMock()
    session.__aexit__ = AsyncMock()
    return session


class TestListTools:
    @pytest.mark.asyncio
    async def test_returns_four_tools(self):
        tools = await list_tools()
        assert len(tools) == 4

    @pytest.mark.asyncio
    async def test_tool_names(self):
        tools = await list_tools()
        names = {t.name for t in tools}
        assert names == {"get_quotes", "get_fundamentals", "get_earnings", "sync_symbol"}


class TestCallToolRouting:
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        result = await call_tool("nonexistent", {})
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        payload = json.loads(result[0].text)
        assert "error" in payload

    @pytest.mark.asyncio
    async def test_get_quotes_returns_text_content(self):
        with patch(
            "ibkr_mcp_service.mcp.server.handle_quote",
            new_callable=AsyncMock,
        ) as mock_handle:
            mock_handle.return_value = {"symbol": "AAPL", "bars": []}
            result = await call_tool("get_quotes", {"symbol": "AAPL"})
            assert len(result) == 1
            assert isinstance(result[0], TextContent)
            mock_handle.assert_called_once_with({"symbol": "AAPL"})

    @pytest.mark.asyncio
    async def test_get_fundamentals_routes_correctly(self):
        with patch(
            "ibkr_mcp_service.mcp.server.handle_fundamentals",
            new_callable=AsyncMock,
        ) as mock_handle:
            mock_handle.return_value = {"symbol": "MSFT", "xml_data": "<xml>"}
            result = await call_tool("get_fundamentals", {"symbol": "MSFT"})
            mock_handle.assert_called_once_with({"symbol": "MSFT"})

    @pytest.mark.asyncio
    async def test_get_earnings_routes_correctly(self):
        with patch(
            "ibkr_mcp_service.mcp.server.handle_get_earnings",
            new_callable=AsyncMock,
        ) as mock_handle:
            mock_handle.return_value = {"symbol": "TSLA", "xml_data": "<xml>"}
            result = await call_tool("get_earnings", {"symbol": "TSLA"})
            mock_handle.assert_called_once_with({"symbol": "TSLA"})

    @pytest.mark.asyncio
    async def test_sync_symbol_routes_correctly(self):
        with patch(
            "ibkr_mcp_service.mcp.server.handle_sync_symbol",
            new_callable=AsyncMock,
        ) as mock_handle:
            mock_handle.return_value = {"symbol": "NVDA", "synced": True}
            result = await call_tool("sync_symbol", {"symbol": "NVDA"})
            mock_handle.assert_called_once_with({"symbol": "NVDA"})


class TestGetEarningsHandler:
    @pytest.mark.asyncio
    async def test_returns_model_dump(self):
        with (
            patch("ibkr_mcp_service.mcp.tools.get_earnings.get_session_factory") as mock_factory,
            patch("ibkr_mcp_service.mcp.tools.get_earnings.get_ibkr_client") as mock_ibkr,
            patch("ibkr_mcp_service.mcp.tools.get_earnings.EarningsService") as MockSvc,
        ):
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock()
            mock_session.__aexit__ = AsyncMock()
            mock_factory.return_value = MagicMock()
            mock_factory.return_value.return_value = mock_session

            svc_instance = AsyncMock()
            mock_result = MagicMock()
            mock_result.model_dump.return_value = {"symbol": "AAPL", "xml_data": "<xml>"}
            svc_instance.get_earnings = AsyncMock(return_value=mock_result)
            MockSvc.return_value = svc_instance

            result = await handle_get_earnings({"symbol": "AAPL"})

            assert result == {"symbol": "AAPL", "xml_data": "<xml>"}
            svc_instance.get_earnings.assert_called_once()


class TestSyncSymbolHandler:
    @pytest.mark.asyncio
    async def test_syncs_all_three_data_types(self):
        with (
            patch("ibkr_mcp_service.mcp.tools.get_earnings.get_session_factory") as mock_factory,
            patch("ibkr_mcp_service.mcp.tools.get_earnings.get_ibkr_client") as mock_ibkr,
            patch("ibkr_mcp_service.mcp.tools.get_earnings.QuoteService") as MockQS,
            patch("ibkr_mcp_service.mcp.tools.get_earnings.FundamentalsService") as MockFS,
            patch("ibkr_mcp_service.mcp.tools.get_earnings.EarningsService") as MockES,
        ):
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock()
            mock_session.__aexit__ = AsyncMock()
            mock_factory.return_value = MagicMock()
            mock_factory.return_value.return_value = mock_session

            qs_instance = AsyncMock()
            quotes_resp = MagicMock()
            quotes_resp.bars = [1, 2, 3]
            qs_instance.get_quotes = AsyncMock(return_value=quotes_resp)
            MockQS.return_value = qs_instance

            fs_instance = AsyncMock()
            fund_resp = MagicMock()
            fund_resp.xml_data = "<xml>fund</xml>"
            fs_instance.get_fundamentals = AsyncMock(return_value=fund_resp)
            MockFS.return_value = fs_instance

            es_instance = AsyncMock()
            earn_resp = MagicMock()
            earn_resp.xml_data = "<xml>earn</xml>"
            es_instance.get_earnings = AsyncMock(return_value=earn_resp)
            MockES.return_value = es_instance

            result = await handle_sync_symbol({"symbol": "AAPL"})

            assert result["symbol"] == "AAPL"
            assert result["synced"] is True
            assert result["bars"] == 3
            assert result["fundamentals"] is True
            assert result["earnings"] is True

            qs_instance.get_quotes.assert_called_once()
            fs_instance.get_fundamentals.assert_called_once()
            es_instance.get_earnings.assert_called_once()

    @pytest.mark.asyncio
    async def test_force_refresh_passed_to_services(self):
        with (
            patch("ibkr_mcp_service.mcp.tools.get_earnings.get_session_factory") as mock_factory,
            patch("ibkr_mcp_service.mcp.tools.get_earnings.get_ibkr_client") as mock_ibkr,
            patch("ibkr_mcp_service.mcp.tools.get_earnings.QuoteService") as MockQS,
            patch("ibkr_mcp_service.mcp.tools.get_earnings.FundamentalsService") as MockFS,
            patch("ibkr_mcp_service.mcp.tools.get_earnings.EarningsService") as MockES,
        ):
            mock_factory.return_value = MagicMock()
            mock_factory.return_value.return_value = MagicMock()
            mock_factory.return_value.return_value.__aenter__ = AsyncMock()
            mock_factory.return_value.return_value.__aexit__ = AsyncMock()

            qs_instance = AsyncMock()
            quotes_resp = MagicMock()
            quotes_resp.bars = []
            qs_instance.get_quotes = AsyncMock(return_value=quotes_resp)
            MockQS.return_value = qs_instance

            fs_instance = AsyncMock()
            fund_resp = MagicMock()
            fund_resp.xml_data = ""
            fs_instance.get_fundamentals = AsyncMock(return_value=fund_resp)
            MockFS.return_value = fs_instance

            es_instance = AsyncMock()
            earn_resp = MagicMock()
            earn_resp.xml_data = ""
            es_instance.get_earnings = AsyncMock(return_value=earn_resp)
            MockES.return_value = es_instance

            await handle_sync_symbol({"symbol": "NVDA"})

            _, qkwargs = qs_instance.get_quotes.call_args
            assert qkwargs.get("force_refresh") is True

            _, fkwargs = fs_instance.get_fundamentals.call_args
            assert fkwargs.get("force_refresh") is True

            _, ekwargs = es_instance.get_earnings.call_args
            assert ekwargs.get("force_refresh") is True


class TestGetQuotesHandler:
    @pytest.mark.asyncio
    async def test_returns_model_dump(self):
        with (
            patch("ibkr_mcp_service.mcp.tools.get_quote.get_session_factory") as mock_factory,
            patch("ibkr_mcp_service.mcp.tools.get_quote.get_ibkr_client") as mock_ibkr,
            patch("ibkr_mcp_service.mcp.tools.get_quote.QuoteService") as MockSvc,
        ):
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock()
            mock_session.__aexit__ = AsyncMock()
            mock_factory.return_value = MagicMock()
            mock_factory.return_value.return_value = mock_session

            svc_instance = AsyncMock()
            mock_result = MagicMock()
            mock_result.model_dump.return_value = {"symbol": "AAPL", "bars": []}
            svc_instance.get_quotes = AsyncMock(return_value=mock_result)
            MockSvc.return_value = svc_instance

            result = await handle_quote({"symbol": "AAPL"})

            assert result == {"symbol": "AAPL", "bars": []}
            svc_instance.get_quotes.assert_called_once()


class TestGetFundamentalsHandler:
    @pytest.mark.asyncio
    async def test_returns_model_dump(self):
        with (
            patch("ibkr_mcp_service.mcp.tools.get_fundamental.get_session_factory") as mock_factory,
            patch("ibkr_mcp_service.mcp.tools.get_fundamental.get_ibkr_client") as mock_ibkr,
            patch("ibkr_mcp_service.mcp.tools.get_fundamental.FundamentalsService") as MockSvc,
        ):
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock()
            mock_session.__aexit__ = AsyncMock()
            mock_factory.return_value = MagicMock()
            mock_factory.return_value.return_value = mock_session

            svc_instance = AsyncMock()
            mock_result = MagicMock()
            mock_result.model_dump.return_value = {"symbol": "MSFT", "xml_data": "<x>"}
            svc_instance.get_fundamentals = AsyncMock(return_value=mock_result)
            MockSvc.return_value = svc_instance

            result = await handle_fundamentals({"symbol": "MSFT"})

            assert result == {"symbol": "MSFT", "xml_data": "<x>"}
            svc_instance.get_fundamentals.assert_called_once()
