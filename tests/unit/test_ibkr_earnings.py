import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ibkr_mcp_service.ibkr.client import IBKRClient
from ibkr_mcp_service.ibkr.earnings import get_earnings_data


class TestGetEarningsData:
    def make_client(self):
        client = MagicMock(spec=IBKRClient)
        client.lock = MagicMock()
        client.lock.__aenter__ = AsyncMock()
        client.lock.__aexit__ = AsyncMock()
        client._ib = MagicMock()
        client._ib.reqFundamentalDataAsync = AsyncMock(return_value="<xml>earnings</xml>")
        return client

    @pytest.mark.asyncio
    async def test_delegates_to_fundamental_data_with_calendar_report(self):
        client = self.make_client()
        contract = MagicMock()

        result = await get_earnings_data(client, contract)

        assert result == "<xml>earnings</xml>"
        client._ib.reqFundamentalDataAsync.assert_called_once_with(
            contract, reportType="CalendarReport",
        )

    @pytest.mark.asyncio
    async def test_uses_lock(self):
        client = self.make_client()
        contract = MagicMock()

        await get_earnings_data(client, contract)

        client.lock.__aenter__.assert_called()
