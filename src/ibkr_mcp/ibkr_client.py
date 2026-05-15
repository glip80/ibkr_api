"""
Async IBKR client wrapper around ib_async.

Reference: https://github.com/ib-api-reloaded/ib_async

Manages connection lifecycle and exposes typed methods for:
  - Historical bars (OHLCV) via reqHistoricalDataAsync
  - Fundamental data (financials) via reqFundamentalDataAsync
  - Earnings / analyst estimates (RESC report) via reqFundamentalDataAsync
"""

import logging
from typing import Any

from ib_async import IB, Stock, util
from ib_async.contract import Contract
from ib_async.objects import BarData

logger = logging.getLogger(__name__)

# Default connection parameters — override via Config / env vars
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 7497      # 7497 = TWS paper-trading; 7496 = TWS live; 4001 = IB Gateway
_DEFAULT_CLIENT_ID = 1
_DEFAULT_TIMEOUT = 30     # seconds


class IBKRClient:
    """Thin async wrapper around :class:`ib_async.IB`.

    Parameters
    ----------
    host:
        TWS / IB Gateway host address.
    port:
        API port. Use ``7497`` for TWS paper, ``7496`` for TWS live,
        ``4001`` for IB Gateway.
    client_id:
        Unique integer client identifier. Every simultaneous connection
        to the same TWS session needs a different ID.
    timeout:
        Seconds to wait for a connect / request response.
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

    # ── connection ────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Establish connection to TWS / IB Gateway (no-op if already connected)."""
        if self._ib.isConnected():
            logger.debug("Already connected to IBKR at %s:%s", self.host, self.port)
            return
        logger.info(
            "Connecting to IBKR at %s:%s (clientId=%s)", self.host, self.port, self.client_id
        )
        # connectAsync signature:
        #   connectAsync(host, port, clientId, timeout=4, readonly=False, account='')
        await self._ib.connectAsync(
            self.host,
            self.port,
            clientId=self.client_id,
            timeout=self.timeout,
        )
        logger.info("Connected to IBKR")

    async def disconnect(self) -> None:
        """Gracefully close the connection."""
        if self._ib.isConnected():
            self._ib.disconnect()
            logger.info("Disconnected from IBKR")

    async def __aenter__(self) -> "IBKRClient":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.disconnect()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _make_stock(self, symbol: str, exchange: str = "SMART", currency: str = "USD") -> Stock:
        """Construct a :class:`ib_async.Stock` contract."""
        return Stock(symbol.upper(), exchange, currency)

    async def _qualify(self, contract: Contract) -> Contract:
        """Resolve a contract against IBKR servers.

        Raises
        ------
        ValueError
            When IBKR cannot find a matching contract.
        """
        contracts = await self._ib.qualifyContractsAsync(contract)
        if not contracts:
            raise ValueError(f"Could not qualify contract for symbol '{contract.symbol}'")
        logger.debug("Qualified contract: %s (conId=%s)", contract.symbol, contracts[0].conId)
        return contracts[0]

    # ── historical bars ───────────────────────────────────────────────────────

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
        """Fetch historical OHLCV bars from IBKR.

        Wraps ``IB.reqHistoricalDataAsync``.

        Parameters
        ----------
        symbol:
            Ticker, e.g. ``"AAPL"``.
        end_datetime:
            End of the requested period in TWS format ``"YYYYMMDD HH:MM:SS"``
            or ``""`` for *now*.
        duration:
            How far back to go — ``"1 Y"``, ``"6 M"``, ``"30 D"``, ``"5 D"``.
            Full list in IBKR docs: Historical Data Duration String.
        bar_size:
            Bar granularity — ``"1 day"``, ``"1 hour"``, ``"30 mins"``,
            ``"5 mins"``, ``"1 min"``.
            Full list: Historical Bar Size Settings.
        what_to_show:
            ``"ADJUSTED_LAST"`` (split+dividend adjusted close) |
            ``"TRADES"`` (unadjusted last trade price) |
            ``"MIDPOINT"`` | ``"BID"`` | ``"ASK"``.
        use_rth:
            ``True`` = regular trading hours only (default).
        exchange:
            IBKR routing exchange (default ``"SMART"``).
        currency:
            ISO currency code (default ``"USD"``).

        Returns
        -------
        list[dict]
            Each dict contains: ``date``, ``open``, ``high``, ``low``,
            ``close``, ``volume``, ``average``, ``bar_count``.
        """
        contract = await self._qualify(self._make_stock(symbol, exchange, currency))
        logger.info(
            "reqHistoricalData: symbol=%s duration=%s bar_size=%s what_to_show=%s use_rth=%s",
            symbol, duration, bar_size, what_to_show, use_rth,
        )

        # reqHistoricalDataAsync signature:
        #   reqHistoricalDataAsync(
        #       contract, endDateTime, durationStr, barSizeSetting,
        #       whatToShow, useRTH, formatDate=1, keepUpToDate=False, chartOptions=[]
        #   )
        bars: list[BarData] = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end_datetime,
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=what_to_show,
            useRTH=use_rth,
            formatDate=1,        # 1 = "YYYYMMDD HH:MM:SS" string; 2 = epoch seconds
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

    # ── fundamental data ──────────────────────────────────────────────────────

    async def get_fundamentals(
        self,
        symbol: str,
        report_type: str = "ReportsFinSummary",
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> str:
        """Fetch fundamental data XML from IBKR.

        Wraps ``IB.reqFundamentalDataAsync``.

        Parameters
        ----------
        symbol:
            Ticker, e.g. ``"AAPL"``.
        report_type:
            One of:

            * ``"ReportsFinSummary"`` — financial highlights (income, balance sheet, cash flow)
            * ``"ReportSnapshot"``    — company overview snapshot
            * ``"ReportsOwnership"``  — institutional ownership report
            * ``"CalendarReport"``    — earnings calendar dates
            * ``"RESC"``              — analyst estimates / consensus EPS

            Note: availability depends on your IBKR market data subscriptions.
        exchange:
            Routing exchange.
        currency:
            Currency denomination.

        Returns
        -------
        str
            Raw XML string from IBKR Refinitiv/Morningstar data feed.
        """
        contract = await self._qualify(self._make_stock(symbol, exchange, currency))
        logger.info(
            "reqFundamentalData: symbol=%s report_type=%s", symbol, report_type
        )

        # reqFundamentalDataAsync signature:
        #   reqFundamentalDataAsync(contract, reportType, fundamentalDataOptions=[])
        xml: str = await self._ib.reqFundamentalDataAsync(
            contract,
            reportType=report_type,
        )
        if not xml:
            raise ValueError(
                f"Empty fundamental data for {symbol}/{report_type}. "
                "Check your IBKR market data subscriptions."
            )
        return xml

    # ── earnings ──────────────────────────────────────────────────────────────

    async def get_earnings(
        self,
        symbol: str,
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> str:
        """Fetch earnings / analyst estimate data (RESC report) for *symbol*.

        The RESC report contains historical EPS actuals and forward analyst
        consensus estimates.  Returns raw XML; callers should parse with
        ``xml.etree.ElementTree`` or store as-is.
        """
        logger.info("get_earnings: symbol=%s (RESC report)", symbol)
        return await self.get_fundamentals(
            symbol,
            report_type="RESC",
            exchange=exchange,
            currency=currency,
        )

    # ── market data type ──────────────────────────────────────────────────────

    def set_market_data_type(self, data_type: int = 1) -> None:
        """Configure market data subscription type.

        Must be called **after** connecting.

        Parameters
        ----------
        data_type:
            * ``1`` — Real-time (requires live subscription)
            * ``2`` — Frozen (last available real-time snapshot)
            * ``3`` — Delayed (~15 min, no subscription required)
            * ``4`` — Delayed frozen (last available delayed data)

        Notes
        -----
        For historical data this setting has no effect; it only applies
        to :meth:`ib_async.IB.reqMktData` live-streaming calls.
        Call with ``data_type=3`` during development if you lack a
        live data subscription.

        Example
        -------
        >>> client.set_market_data_type(3)   # use free delayed data
        """
        self._ib.reqMarketDataType(data_type)
        logger.info("Market data type set to %d", data_type)
