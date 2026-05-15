"""
Background synchronisation scheduler.

Periodically refreshes cached data for a configured list of symbols so
that MCP tool calls return near-real-time data without always hitting IBKR.

Usage
-----
Start the scheduler alongside the MCP server::

    scheduler = SyncScheduler(ibkr_client, store, symbols=["AAPL", "MSFT"])
    await scheduler.start()
    # ... run MCP server ...
    await scheduler.stop()
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable

from ibkr_mcp.ibkr_client import IBKRClient
from ibkr_mcp.persistence import PersistenceStore, _utcnow

logger = logging.getLogger(__name__)


class SyncScheduler:
    """Periodic background sync for a list of symbols.

    Parameters
    ----------
    client:
        Connected :class:`IBKRClient` instance.
    store:
        Initialised :class:`PersistenceStore` instance.
    symbols:
        Tickers to sync on each cycle.
    interval_seconds:
        How often (in seconds) to run a full sync cycle.
    bar_size:
        Bar size for quote sync (default ``"1 day"``).
    duration:
        Duration string for quote sync (default ``"1 Y"``).
    what_to_show:
        Data type for quote sync (default ``"ADJUSTED_LAST"``).
    """

    def __init__(
        self,
        client: IBKRClient,
        store: PersistenceStore,
        symbols: list[str],
        interval_seconds: int = 3600,
        bar_size: str = "1 day",
        duration: str = "1 Y",
        what_to_show: str = "ADJUSTED_LAST",
    ) -> None:
        self.client = client
        self.store = store
        self.symbols = [s.upper() for s in symbols]
        self.interval_seconds = interval_seconds
        self.bar_size = bar_size
        self.duration = duration
        self.what_to_show = what_to_show
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Launch the background sync loop."""
        logger.info(
            "Starting sync scheduler: symbols=%s interval=%ss",
            self.symbols,
            self.interval_seconds,
        )
        self._task = asyncio.create_task(self._loop(), name="ibkr-sync")

    async def stop(self) -> None:
        """Cancel the background sync loop."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Sync scheduler stopped")

    # ── private ──────────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        """Run sync immediately, then every *interval_seconds*."""
        while True:
            await self._run_all()
            await asyncio.sleep(self.interval_seconds)

    async def _run_all(self) -> None:
        """Sync all symbols sequentially to avoid overwhelming TWS."""
        logger.info("Sync cycle started for %d symbols", len(self.symbols))
        for symbol in self.symbols:
            await self._sync_symbol(symbol)
        logger.info("Sync cycle completed")

    async def _sync_symbol(self, symbol: str) -> None:
        """Sync quotes + fundamentals + earnings for one symbol."""
        for data_type, coro_fn in [
            ("quotes", self._sync_quotes),
            ("fundamentals", self._sync_fundamentals),
            ("earnings", self._sync_earnings),
        ]:
            started = _utcnow()
            try:
                await coro_fn(symbol)
                await self.store.log_sync(symbol, data_type, "ok", None, started)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Sync failed for %s/%s: %s", symbol, data_type, exc)
                await self.store.log_sync(symbol, data_type, "error", str(exc), started)

    async def _sync_quotes(self, symbol: str) -> None:
        bars = await self.client.get_historical_bars(
            symbol,
            duration=self.duration,
            bar_size=self.bar_size,
            what_to_show=self.what_to_show,
        )
        await self.store.upsert_quotes(symbol, self.bar_size, self.what_to_show, bars)

    async def _sync_fundamentals(self, symbol: str) -> None:
        xml = await self.client.get_fundamentals(symbol)
        await self.store.upsert_fundamentals(symbol, "ReportsFinSummary", xml)

    async def _sync_earnings(self, symbol: str) -> None:
        xml = await self.client.get_earnings(symbol)
        await self.store.upsert_earnings(symbol, xml)
