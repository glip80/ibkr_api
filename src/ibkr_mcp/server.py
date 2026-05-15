"""
MCP server exposing IBKR market data as tools.

Tools
-----
get_quotes
    Historical OHLCV bars with configurable period, interval and adjust flag.
get_fundamentals
    Financial summary XML for a symbol.
get_earnings
    Earnings / analyst estimates XML for a symbol.
get_sync_log
    Inspect recent background-sync activity.
trigger_sync
    Force an immediate refresh for a symbol.

The server uses a cache-first strategy:
  1. Check the SQLite cache.
  2. If the cache is fresh → return cached data.
  3. If stale (or missing) → fetch from IBKR, store, return.
"""

import logging
import os
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    TextContent,
    Tool,
)

from ibkr_mcp.config import settings
from ibkr_mcp.ibkr_client import IBKRClient
from ibkr_mcp.logging_config import configure_logging
from ibkr_mcp.persistence import PersistenceStore
from ibkr_mcp.sync import SyncScheduler

logger = logging.getLogger(__name__)

# ── tool input schemas ────────────────────────────────────────────────────────

_TOOLS: list[Tool] = [
    Tool(
        name="get_quotes",
        description=(
            "Fetch historical OHLCV bars for a stock symbol from IBKR. "
            "Returns cached data when fresh; re-fetches when stale."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Ticker symbol, e.g. 'AAPL'.",
                },
                "duration": {
                    "type": "string",
                    "description": "How far back to go, e.g. '1 Y', '6 M', '30 D'. Default '1 Y'.",
                    "default": "1 Y",
                },
                "bar_size": {
                    "type": "string",
                    "description": "Bar granularity, e.g. '1 day', '1 hour', '5 mins'. Default '1 day'.",
                    "default": "1 day",
                },
                "what_to_show": {
                    "type": "string",
                    "description": "Data type: 'ADJUSTED_LAST' | 'TRADES' | 'MIDPOINT'. Default 'ADJUSTED_LAST'.",
                    "default": "ADJUSTED_LAST",
                },
                "use_rth": {
                    "type": "boolean",
                    "description": "Regular trading hours only. Default true.",
                    "default": True,
                },
                "end_datetime": {
                    "type": "string",
                    "description": "End of the period as 'YYYYMMDD HH:MM:SS'. Empty = now.",
                    "default": "",
                },
                "exchange": {
                    "type": "string",
                    "description": "Routing exchange. Default 'SMART'.",
                    "default": "SMART",
                },
                "currency": {
                    "type": "string",
                    "description": "Currency code. Default 'USD'.",
                    "default": "USD",
                },
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="get_fundamentals",
        description=(
            "Fetch fundamental financial data (XML) for a stock symbol. "
            "Supports multiple report types."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol."},
                "report_type": {
                    "type": "string",
                    "description": (
                        "Report type: 'ReportsFinSummary' | 'ReportSnapshot' | "
                        "'ReportsOwnership' | 'CalendarReport'. Default 'ReportsFinSummary'."
                    ),
                    "default": "ReportsFinSummary",
                },
                "exchange": {"type": "string", "default": "SMART"},
                "currency": {"type": "string", "default": "USD"},
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="get_earnings",
        description=(
            "Fetch earnings / analyst estimate data (RESC XML) for a stock symbol. "
            "Includes EPS history and forward estimates."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol."},
                "exchange": {"type": "string", "default": "SMART"},
                "currency": {"type": "string", "default": "USD"},
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="get_sync_log",
        description="Return recent background-sync log entries.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of entries to return. Default 50.",
                    "default": 50,
                }
            },
        },
    ),
    Tool(
        name="trigger_sync",
        description="Force an immediate data refresh for a symbol (bypasses cache TTL).",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol."},
                "data_type": {
                    "type": "string",
                    "description": "'quotes' | 'fundamentals' | 'earnings' | 'all'. Default 'all'.",
                    "default": "all",
                },
            },
            "required": ["symbol"],
        },
    ),
]


# ── server factory ────────────────────────────────────────────────────────────

def build_server(
    ibkr_client: IBKRClient,
    store: PersistenceStore,
    scheduler: SyncScheduler | None = None,
) -> Server:
    """Create and configure the MCP :class:`Server`.

    Parameters
    ----------
    ibkr_client:
        Ready-to-use IBKR client (connected or lazily-connecting).
    store:
        Initialised persistence store.
    scheduler:
        Optional background sync scheduler (for ``trigger_sync`` support).
    """
    app = Server(settings.mcp_server_name)

    @app.list_tools()
    async def list_tools() -> ListToolsResult:
        return _TOOLS

    @app.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
        try:
            result = await _dispatch(name, arguments, ibkr_client, store, scheduler)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Tool %s failed: %s", name, exc)
            return [TextContent(type="text", text=f"Error: {exc}")]
        return [TextContent(type="text", text=str(result))]

    return app


# ── tool dispatcher ───────────────────────────────────────────────────────────

async def _dispatch(
    name: str,
    args: dict[str, Any],
    client: IBKRClient,
    store: PersistenceStore,
    scheduler: SyncScheduler | None,
) -> Any:
    """Route tool calls to implementation functions."""
    match name:
        case "get_quotes":
            return await _get_quotes(args, client, store)
        case "get_fundamentals":
            return await _get_fundamentals(args, client, store)
        case "get_earnings":
            return await _get_earnings(args, client, store)
        case "get_sync_log":
            limit = int(args.get("limit", 50))
            return await store.get_sync_log(limit)
        case "trigger_sync":
            return await _trigger_sync(args, client, store)
        case _:
            raise ValueError(f"Unknown tool: {name}")


# ── tool implementations ──────────────────────────────────────────────────────

async def _get_quotes(
    args: dict[str, Any],
    client: IBKRClient,
    store: PersistenceStore,
) -> list[dict[str, Any]]:
    symbol: str = args["symbol"]
    duration: str = args.get("duration", "1 Y")
    bar_size: str = args.get("bar_size", "1 day")
    what_to_show: str = args.get("what_to_show", "ADJUSTED_LAST")
    use_rth: bool = bool(args.get("use_rth", True))
    end_datetime: str = args.get("end_datetime", "")
    exchange: str = args.get("exchange", "SMART")
    currency: str = args.get("currency", "USD")

    cached, is_stale = await store.get_quotes(symbol, bar_size, what_to_show)

    if not is_stale and cached:
        logger.info("Cache hit for quotes %s (%s/%s)", symbol, bar_size, what_to_show)
        return cached

    logger.info("Cache miss / stale for quotes %s — fetching from IBKR", symbol)
    await client.connect()
    bars = await client.get_historical_bars(
        symbol,
        end_datetime=end_datetime,
        duration=duration,
        bar_size=bar_size,
        what_to_show=what_to_show,
        use_rth=use_rth,
        exchange=exchange,
        currency=currency,
    )
    await store.upsert_quotes(symbol, bar_size, what_to_show, bars)
    return bars


async def _get_fundamentals(
    args: dict[str, Any],
    client: IBKRClient,
    store: PersistenceStore,
) -> str:
    symbol: str = args["symbol"]
    report_type: str = args.get("report_type", "ReportsFinSummary")
    exchange: str = args.get("exchange", "SMART")
    currency: str = args.get("currency", "USD")

    cached_xml, is_stale = await store.get_fundamentals(symbol, report_type)

    if not is_stale and cached_xml:
        logger.info("Cache hit for fundamentals %s (%s)", symbol, report_type)
        return cached_xml

    logger.info("Cache miss / stale for fundamentals %s — fetching from IBKR", symbol)
    await client.connect()
    xml = await client.get_fundamentals(symbol, report_type=report_type, exchange=exchange, currency=currency)
    await store.upsert_fundamentals(symbol, report_type, xml)
    return xml


async def _get_earnings(
    args: dict[str, Any],
    client: IBKRClient,
    store: PersistenceStore,
) -> str:
    symbol: str = args["symbol"]
    exchange: str = args.get("exchange", "SMART")
    currency: str = args.get("currency", "USD")

    cached_xml, is_stale = await store.get_earnings(symbol)

    if not is_stale and cached_xml:
        logger.info("Cache hit for earnings %s", symbol)
        return cached_xml

    logger.info("Cache miss / stale for earnings %s — fetching from IBKR", symbol)
    await client.connect()
    xml = await client.get_earnings(symbol, exchange=exchange, currency=currency)
    await store.upsert_earnings(symbol, xml)
    return xml


async def _trigger_sync(
    args: dict[str, Any],
    client: IBKRClient,
    store: PersistenceStore,
) -> dict[str, str]:
    from ibkr_mcp.persistence import _utcnow

    symbol: str = args["symbol"]
    data_type: str = args.get("data_type", "all")
    results: dict[str, str] = {}

    await client.connect()

    async def _do(dtype: str, coro):  # noqa: ANN001
        started = _utcnow()
        try:
            result = await coro
            await store.log_sync(symbol, dtype, "ok", None, started)
            results[dtype] = "ok"
            return result
        except Exception as exc:  # noqa: BLE001
            await store.log_sync(symbol, dtype, "error", str(exc), started)
            results[dtype] = f"error: {exc}"

    if data_type in ("quotes", "all"):
        bars = await _do(
            "quotes",
            client.get_historical_bars(symbol),
        )
        if bars:
            await store.upsert_quotes(symbol, "1 day", "ADJUSTED_LAST", bars)

    if data_type in ("fundamentals", "all"):
        xml = await _do("fundamentals", client.get_fundamentals(symbol))
        if xml:
            await store.upsert_fundamentals(symbol, "ReportsFinSummary", xml)

    if data_type in ("earnings", "all"):
        xml = await _do("earnings", client.get_earnings(symbol))
        if xml:
            await store.upsert_earnings(symbol, xml)

    return results


# ── entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    """Start the MCP server with stdio transport."""
    configure_logging(settings.log_level)

    store = PersistenceStore(
        db_path=settings.db_path,
        quotes_ttl_hours=settings.quotes_ttl_hours,
        fundamentals_ttl_hours=settings.fundamentals_ttl_hours,
    )
    await store.init()

    client = IBKRClient(
        host=settings.ibkr_host,
        port=settings.ibkr_port,
        client_id=settings.ibkr_client_id,
        timeout=settings.ibkr_timeout,
    )

    # Optional: sync a watchlist on startup (comma-separated env var)
    watchlist_env = os.environ.get("SYNC_WATCHLIST", "")
    symbols = [s.strip() for s in watchlist_env.split(",") if s.strip()]
    scheduler: SyncScheduler | None = None
    if symbols:
        await client.connect()
        scheduler = SyncScheduler(
            client,
            store,
            symbols=symbols,
            interval_seconds=settings.sync_interval_seconds,
        )
        await scheduler.start()

    app = build_server(client, store, scheduler)

    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    finally:
        if scheduler:
            await scheduler.stop()
        await client.disconnect()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
