import structlog
from ib_async import Contract

from ibkr_mcp_service.ibkr.client import IBKRClient

log = structlog.get_logger(__name__)


async def get_fundamental_data(client: IBKRClient, contract: Contract, report_type: str) -> str:
    async with client.lock:
        log.info("requesting_fundamental_data", symbol=contract.symbol, type=report_type)
        xml = await client._ib.reqFundamentalDataAsync(contract, reportType=report_type)
        return xml
