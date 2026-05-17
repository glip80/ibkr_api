import structlog
from mcp.types import Tool

from ibkr_mcp_service.db.session import get_session_factory
from ibkr_mcp_service.ibkr.client import get_ibkr_client
from ibkr_mcp_service.models.earnings import EarningsRequest
from ibkr_mcp_service.models.fundamental import FundamentalsRequest
from ibkr_mcp_service.models.quote import QuoteRequest
from ibkr_mcp_service.services.earnings_service import EarningsService
from ibkr_mcp_service.services.fundamentals_service import FundamentalsService
from ibkr_mcp_service.services.quote_service import QuoteService

log = structlog.get_logger(__name__)

GET_EARNINGS_TOOL = Tool(
    name="get_earnings",
    description=(
        "Retrieve IBKR earnings/calendar data for a symbol. "
        "Cached in PostgreSQL after the first request."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "sec_type": {"type": "string", "default": "STK"},
            "exchange": {"type": "string", "default": "SMART"},
            "currency": {"type": "string", "default": "USD"},
        },
        "required": ["symbol"],
    },
)

SYNC_SYMBOL_TOOL = Tool(
    name="sync_symbol",
    description=(
        "Force-refresh cached data for a single symbol from IBKR. "
        "Syncs quotes, fundamentals, and earnings in one call."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Ticker to sync, e.g. AAPL"},
        },
        "required": ["symbol"],
    },
)


async def handle_get_earnings(args: dict) -> dict:
    factory = get_session_factory()
    ibkr = get_ibkr_client()
    async with factory() as session:
        req = EarningsRequest(**args)
        svc = EarningsService(session, ibkr)
        result = await svc.get_earnings(req)
        return result.model_dump(mode="json")


async def handle_sync_symbol(args: dict) -> dict:
    symbol = args["symbol"]
    factory = get_session_factory()
    ibkr = get_ibkr_client()
    async with factory() as session:
        qsvc = QuoteService(session, ibkr)
        fsvc = FundamentalsService(session, ibkr)
        esvc = EarningsService(session, ibkr)

        quotes = await qsvc.get_quotes(QuoteRequest(symbol=symbol), force_refresh=True)
        fund = await fsvc.get_fundamentals(FundamentalsRequest(symbol=symbol), force_refresh=True)
        earn = await esvc.get_earnings(EarningsRequest(symbol=symbol), force_refresh=True)

    return {
        "symbol": symbol,
        "synced": True,
        "bars": len(quotes.bars),
        "fundamentals": bool(fund.xml_data),
        "earnings": bool(earn.xml_data),
    }
