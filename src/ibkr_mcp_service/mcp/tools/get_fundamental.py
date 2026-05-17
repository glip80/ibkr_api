import structlog
from mcp.types import Tool

from ibkr_mcp_service.db.session import get_session_factory
from ibkr_mcp_service.ibkr.client import get_ibkr_client
from ibkr_mcp_service.models.fundamental import FundamentalsRequest
from ibkr_mcp_service.services.fundamentals_service import FundamentalsService

log = structlog.get_logger(__name__)

GET_FUNDAMENTALS_TOOL = Tool(
    name="get_fundamentals",
    description=(
        "Retrieve IBKR fundamental data XML for a symbol. "
        "Cached in PostgreSQL after the first request."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "sec_type": {"type": "string", "default": "STK"},
            "exchange": {"type": "string", "default": "SMART"},
            "currency": {"type": "string", "default": "USD"},
            "report_type": {
                "type": "string",
                "default": "ReportsFinSummary",
                "enum": [
                    "ReportsFinSummary", "ReportSnapshot",
                    "ReportsOwnership", "ReportRatios",
                    "CalendarReport", "RESC",
                ],
            },
        },
        "required": ["symbol"],
    },
)


async def handle(args: dict) -> dict:
    factory = get_session_factory()
    ibkr = get_ibkr_client()
    async with factory() as session:
        req = FundamentalsRequest(**args)
        svc = FundamentalsService(session, ibkr)
        result = await svc.get_fundamentals(req)
        return result.model_dump(mode="json")
