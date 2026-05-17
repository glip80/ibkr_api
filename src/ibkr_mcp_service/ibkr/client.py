import asyncio
from functools import lru_cache

import structlog
from ib_async import IB, Contract
from tenacity import retry, stop_after_attempt, wait_exponential

from ibkr_mcp_service.config import get_settings

log = structlog.get_logger(__name__)


class IBKRClient:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._ib = IB()
        self._lock = asyncio.Lock()

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock

    async def connect(self) -> None:
        await self._connect_with_retry()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _connect_with_retry(self) -> None:
        if not self._ib.isConnected():
            log.info(
                "connecting_to_ibkr",
                host=self._settings.ibkr_host,
                port=self._settings.ibkr_port,
            )
            await self._ib.connectAsync(
                self._settings.ibkr_host,
                self._settings.ibkr_port,
                clientId=self._settings.ibkr_client_id,
                timeout=self._settings.ibkr_timeout,
            )
            log.info("connected_to_ibkr")

    async def disconnect(self) -> None:
        if self._ib.isConnected():
            self._ib.disconnect()
            log.info("disconnected_from_ibkr")

    def make_contract(
        self, symbol: str, sec_type: str = "STK",
        exchange: str = "SMART", currency: str = "USD",
    ) -> Contract:
        return Contract(symbol=symbol, secType=sec_type, exchange=exchange, currency=currency)


@lru_cache
def get_ibkr_client() -> IBKRClient:
    return IBKRClient()
