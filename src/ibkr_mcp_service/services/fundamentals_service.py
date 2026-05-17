import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ibkr_mcp_service.ibkr.client import IBKRClient
from ibkr_mcp_service.ibkr.fundamentals import get_fundamental_data
from ibkr_mcp_service.models.fundamental import FundamentalsRequest, FundamentalsResponse
from ibkr_mcp_service.repositories.fundamental_repo import FundamentalsRepository

log = structlog.get_logger(__name__)


class FundamentalsService:
    def __init__(self, session: AsyncSession, ibkr: IBKRClient) -> None:
        self._fund_repo = FundamentalsRepository(session)
        self._ibkr = ibkr

    async def get_fundamentals(
        self, req: FundamentalsRequest, force_refresh: bool = False
    ) -> FundamentalsResponse:
        if not force_refresh:
            cached = await self._fund_repo.get(req.symbol, req.report_type)
            if cached:
                log.info("cache_hit_fundamentals", symbol=req.symbol)
                return FundamentalsResponse(
                    symbol=req.symbol,
                    report_type=req.report_type,
                    xml_data=cached.xml_data,
                    cached=True,
                    fetched_at=cached.fetched_at,
                )

        contract = self._ibkr.make_contract(
            symbol=req.symbol, sec_type=req.sec_type.value,
            exchange=req.exchange, currency=req.currency,
        )
        xml = await get_fundamental_data(self._ibkr, contract, req.report_type)
        response = FundamentalsResponse(
            symbol=req.symbol, report_type=req.report_type, xml_data=xml,
            sec_type=req.sec_type.value, currency=req.currency,
        )
        await self._fund_repo.upsert(response)
        return response
