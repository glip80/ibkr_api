"""
Async IBKR client wrapper around ib_async.

Manages connection lifecycle and exposes typed methods for:
  - Historical bars (OHLCV)
  - Fundamental data (financials summary)
  - Earnings calendar / EPS history
"""

import logging
from datetime import datetime, timezone
from typing import Any

from ib_async import IB, Contract, Stock, BarData, util

logger = logging.getLogger(__name__)

# Default connection parameters — override via env vars or constructor args
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 7497          # TWS paper-trading port; 4001 for IB Gateway
_DEFAULT_CLIENT_ID = 1
_DEFAULT_TIMEOUT = 30         # seconds to wait for a response


class IBKRClient:
    """Thin async wrapper around :class:`ib_async.IB`.

    Parameters
    ----------
    host:
        TWS / IB Gateway host address.
    port:
        TWS / IB Gateway port (7496 live, 7497 paper, 4001 gateway).
    client_id:
        Unique client identifier.  Multiple clients need distinct IDs.
    timeout:
        Request timeout in seconds.
    """

    def __init__(
        self,
        host: str = _DEFAULT_HOST,
        port: int = _DEFAULT_PORT,
        client_id: int = _DEFAULT_CLIENT_ID,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.timeout = timeout
        self._ib = IB()

    # ── connection helpers ───────────────────────────────────────────────────

    async def connect(self) -> None:
        """Establish connection to TWS / IB Gateway."""
        if self._ib.isConnected():
            logger.debug("Already connected to IBKR")
            return
        logger.info("Connecting to IBKR %s:%s (client_id=%s)", self.host, self.port, self.client_id)
        await self._ib.connectAsync(self.host, self.port, clientId=self.client_id, timeout=self.timeout)
        logger.info("Connected to IBKR")

    async def disconnect(self) -> None:
        """Gracefully close the IBKR connection."""
        if self._ib.isConnected():
            self._ib.disconnect()
            logger.info("Disconnected from IBKR")

    async def __aenter__(self) -> "IBKRClient":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.disconnect()

    # ── contract resolution ──────────────────────────────────────────────────

    def _stock_contract(self, symbol: str, exchange: str = "SMART", currency: str = "USD") -> Stock:
        """Build a :class:`ib_async.Stock` contract for *symbol*."""
        return Stock(symbol.upper(), exchange, currency)

    async def _qualify(self, contract: Contract) -> Contract:
        """Resolve and validate a contract against IBKR servers."""
        contracts = await self._ib.qualifyContractsAsync(contract)
        if not contracts:
            raise ValueError(f"Could not qualify contract: {contract.symbol}")
        return contracts[0]

    # ── historical bars ──────────────────────────────────────────────────────

    async def get_historical_bars(
        self,
        symbol: str,
        end_datetime: str = "",
        duration: str = "1 Y",
        bar_size: str = "1 day",
        what_to_show: str = "ADJUSTED_LAST",
        use_rth: bool = True,
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> list[dict[str, Any]]:
        """Fetch OHLCV bars from IBKR.

        Parameters
        ----------
        symbol:
            Ticker symbol (e.g. ``"AAPL"``).
        end_datetime:
            End of the requested period (``"YYYYMMDD HH:MM:SS"``).
            Empty string means *now*.
        duration:
            How far back to go (``"1 Y"``, ``"6 M"``, ``"30 D"``).
        bar_size:
            Bar granularity (``"1 min"``, ``"5 mins"``, ``"1 hour"``, ``"1 day"``).
        what_to_show:
            Data type — ``"ADJUSTED_LAST"`` | ``"TRADES"`` | ``"MIDPOINT"``.
        use_rth:
            ``True`` = regular trading hours only.
        exchange:
            Routing exchange (default ``"SMART"``).
        currency:
            Currency denomination (default ``"USD"``).

        Returns
        -------
        list[dict]
            Each dict has keys: ``date``, ``open``, ``high``, ``low``,
            ``close``, ``volume``, ``average``, ``barCount``.
        """
        contract = await self._qualify(self._stock_contract(symbol, exchange, currency))
        logger.info(
            "Requesting historical bars: symbol=%s duration=%s bar_size=%s what_to_show=%s",
            symbol, duration, bar_size, what_to_show,
        )
        bars: list[BarData] = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end_datetime,
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=what_to_show,
            useRTH=use_rth,
            formatDate=1,
            keepUpToDate=False,
        )
        return [
            {
                "date": str(b.date),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "average": b.average,
                "bar_count": b.barCount,
            }
            for b in bars
        ]

    # ── fundamental data ─────────────────────────────────────────────────────

    async def get_fundamentals(
        self,
        symbol: str,
        report_type: str = "ReportsFinSummary",
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> str:
        """Fetch fundamental data XML for *symbol*.

        Parameters
        ----------
        symbol:
            Ticker symbol.
        report_type:
            One of ``"ReportsFinSummary"``, ``"ReportsOwnership"``,
            ``"ReportSnapshot"``, ``"RESC"`` (analyst estimates),
            ``"CalendarReport"`` (earnings calendar).
        exchange:
            Routing exchange.
        currency:
            Currency.

        Returns
        -------
        str
            Raw XML string from IBKR.
        """
        contract = await self._qualify(self._stock_contract(symbol, exchange, currency))
        logger.info("Requesting fundamentals: symbol=%s report_type=%s", symbol, report_type)
        xml: str = await self._ib.reqFundamentalDataAsync(contract, reportType=report_type)
        return xml

    # ── earnings ─────────────────────────────────────────────────────────────

    async def get_earnings(
        self,
        symbol: str,
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> str:
        """Fetch earnings / analyst estimate XML (RESC report) for *symbol*.

        Returns raw XML; callers should parse with the utility helpers or
        store as-is for later XML parsing.
        """
        return await self.get_fundamentals(symbol, report_type="RESC", exchange=exchange, currency=currency)
