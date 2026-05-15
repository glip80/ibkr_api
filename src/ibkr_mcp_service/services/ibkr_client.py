"""ib_async wrapper for managing the connection to TWS/Gateway."""

import asyncio
from functools import lru_cache

import structlog
from ib_async import IB, BarDataList, Contract
from tenacity import retry, stop_after_attempt, wait_exponential

from ibkr_mcp_service.config import get_settings

log = structlog.get_logger(__name__)


class IBKRClient:
    """Manages the lifecycle of an ib_async IB connection."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._ib = IB()
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Connect to TWS or IB Gateway with retries."""
        await self._connect_with_retry()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _connect_with_retry(self) -> None:
        if not self._ib.isConnected():
            log.info("connecting_to_ibkr", host=self._settings.ibkr_host, port=self._settings.ibkr_port)
            await self._ib.connectAsync(
                self._settings.ibkr_host,
                self._settings.ibkr_port,
                clientId=self._settings.ibkr_client_id,
                timeout=self._settings.ibkr_timeout,
            )
            log.info("connected_to_ibkr")

    async def disconnect(self) -> None:
        """Disconnect safely from the IB API."""
        if self._ib.isConnected():
            self._ib.disconnect()
            log.info("disconnected_from_ibkr")

    def make_contract(
        self, symbol: str, sec_type: str = "STK",
        exchange: str = "SMART", currency: str = "USD",
    ) -> Contract:
        """Utility to create an ib_async Contract object."""
        return Contract(symbol=symbol, secType=sec_type, exchange=exchange, currency=currency)

    async def get_historical_data(
        self, contract: Contract, end_datetime: str, duration_str: str,
        bar_size_setting: str, what_to_show: str, use_rth: bool,
    ) -> BarDataList:
        """Thread-safe call to reqHistoricalDataAsync."""
        async with self._lock:
            log.info("requesting_historical_data", symbol=contract.symbol, duration=duration_str)
            bars = await self._ib.reqHistoricalDataAsync(
                contract,
                endDateTime=end_datetime,
                durationStr=duration_str,
                barSizeSetting=bar_size_setting,
                whatToShow=what_to_show,
                useRTH=use_rth,
                formatDate=1,
                keepUpToDate=False,
            )
            return bars

    async def get_fundamental_data(self, contract: Contract, report_type: str) -> str:
        """Thread-safe call to reqFundamentalDataAsync."""
        async with self._lock:
            log.info("requesting_fundamental_data", symbol=contract.symbol, type=report_type)
            xml = await self._ib.reqFundamentalDataAsync(contract, reportType=report_type)
            return xml


@lru_cache
def get_ibkr_client() -> IBKRClient:
    """Return a singleton IBKRClient instance."""
    return IBKRClient()
