import structlog
from ib_async import Contract

from ibkr_mcp_service.ibkr.client import IBKRClient
from ibkr_mcp_service.ibkr.fundamentals import get_fundamental_data

log = structlog.get_logger(__name__)


async def get_earnings_data(client: IBKRClient, contract: Contract) -> str:
    log.info("requesting_earnings_data", symbol=contract.symbol)
    return await get_fundamental_data(client, contract, "CalendarReport")
