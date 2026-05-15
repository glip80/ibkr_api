"""
Standalone sync script — useful for cron jobs or one-off refreshes.

Usage
-----
    python scripts/run_sync.py AAPL MSFT NVDA

Connects to IBKR, syncs all three data types for each symbol, then exits.
"""

import asyncio
import logging
import sys

from ibkr_mcp.config import settings
from ibkr_mcp.ibkr_client import IBKRClient
from ibkr_mcp.logging_config import configure_logging
from ibkr_mcp.persistence import PersistenceStore, _utcnow


async def sync_symbols(symbols: list[str]) -> None:
    """Sync quotes, fundamentals, and earnings for the given symbols."""
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    store = PersistenceStore(db_path=settings.db_path)
    await store.init()

    async with IBKRClient(
        host=settings.ibkr_host,
        port=settings.ibkr_port,
        client_id=settings.ibkr_client_id,
    ) as client:
        for symbol in symbols:
            for dtype, coro_fn in [
                ("quotes", lambda s: client.get_historical_bars(s)),
                ("fundamentals", lambda s: client.get_fundamentals(s)),
                ("earnings", lambda s: client.get_earnings(s)),
            ]:
                started = _utcnow()
                try:
                    data = await coro_fn(symbol)
                    if dtype == "quotes":
                        await store.upsert_quotes(symbol, "1 day", "ADJUSTED_LAST", data)
                    elif dtype == "fundamentals":
                        await store.upsert_fundamentals(symbol, "ReportsFinSummary", data)
                    else:
                        await store.upsert_earnings(symbol, data)
                    await store.log_sync(symbol, dtype, "ok", None, started)
                    logger.info("Synced %s / %s", symbol, dtype)
                except Exception as exc:  # noqa: BLE001
                    await store.log_sync(symbol, dtype, "error", str(exc), started)
                    logger.error("Failed %s / %s: %s", symbol, dtype, exc)


if __name__ == "__main__":
    symbols = sys.argv[1:] or ["AAPL"]
    asyncio.run(sync_symbols(symbols))
