import structlog
from mcp.types import Tool

from ibkr_mcp_service.db.session import get_session_factory
from ibkr_mcp_service.ibkr.client import get_ibkr_client
from ibkr_mcp_service.models.quote import QuoteRequest
from ibkr_mcp_service.services.quote_service import QuoteService

log = structlog.get_logger(__name__)

GET_QUOTES_TOOL = Tool(
    name="get_quotes",
    description=(
        "Fetch historical OHLCV bars for a symbol from IBKR. "
        "Results are persisted and served from cache on subsequent calls."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Ticker, e.g. AAPL"},
            "sec_type": {
                "type": "string",
                "enum": ["STK", "OPT", "FUT", "IND", "FOP", "CASH", "BAG", "WAR"],
                "default": "STK",
            },
            "exchange": {"type": "string", "default": "SMART"},
            "currency": {"type": "string", "default": "USD"},
            "duration": {
                "type": "string",
                "default": "1 Y",
                "description": "IBKR duration string, e.g. '30 D', '6 M', '1 Y'",
            },
            "bar_size": {
                "type": "string",
                "enum": [
                    "1 sec", "5 secs", "15 secs", "30 secs", "1 min", "2 mins",
                    "3 mins", "5 mins", "15 mins", "30 mins", "1 hour", "2 hours",
                    "3 hours", "4 hours", "8 hours", "1 day", "1 week", "1 month",
                ],
                "default": "1 day",
            },
            "what_to_show": {
                "type": "string",
                "enum": [
                    "TRADES", "MIDPOINT", "BID", "ASK", "BID_ASK",
                    "HISTORICAL_VOLATILITY", "OPTION_IMPLIED_VOLATILITY",
                    "YIELD_ASK", "YIELD_BID", "YIELD_BID_ASK", "YIELD_LAST",
                ],
                "default": "TRADES",
            },
            "use_rth": {"type": "boolean", "default": True},
            "adjusted": {"type": "boolean", "default": True},
            "end_datetime": {
                "type": "string",
                "default": "",
                "description": "End datetime; empty = now",
            },
        },
        "required": ["symbol"],
    },
)


async def handle(args: dict) -> dict:
    factory = get_session_factory()
    ibkr = get_ibkr_client()
    async with factory() as session:
        req = QuoteRequest(**args)
        svc = QuoteService(session, ibkr)
        result = await svc.get_quotes(req)
        return result.model_dump(mode="json")
