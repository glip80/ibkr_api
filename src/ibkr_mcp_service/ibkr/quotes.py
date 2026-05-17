import structlog
from ib_async import BarDataList, Contract

from ibkr_mcp_service.ibkr.client import IBKRClient

log = structlog.get_logger(__name__)


async def get_historical_data(
    client: IBKRClient,
    contract: Contract,
    end_datetime: str,
    duration_str: str,
    bar_size_setting: str,
    what_to_show: str,
    use_rth: bool,
) -> BarDataList:
    async with client.lock:
        log.info("requesting_historical_data", symbol=contract.symbol, duration=duration_str)
        bars = await client._ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end_datetime,
            durationStr=duration_str,
            barSizeSetting=bar_size_setting,
            whatToShow=what_to_show,
            useRTH=use_rth,
            formatDate=1,
            keepUpToDate=False,
        )
        return bars
