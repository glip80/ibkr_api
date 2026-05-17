import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ibkr_mcp_service.ibkr.client import IBKRClient
from ibkr_mcp_service.ibkr.earnings import get_earnings_data
from ibkr_mcp_service.models.earnings import EarningsRequest, EarningsResponse
from ibkr_mcp_service.repositories.earnings_repo import EarningsRepository

log = structlog.get_logger(__name__)


class EarningsService:
    def __init__(self, session: AsyncSession, ibkr: IBKRClient) -> None:
        self._earn_repo = EarningsRepository(session)
        self._ibkr = ibkr

    async def get_earnings(
        self, req: EarningsRequest, force_refresh: bool = False
    ) -> EarningsResponse:
        if not force_refresh:
            cached = await self._earn_repo.get(req.symbol)
            if cached:
                log.info("cache_hit_earnings", symbol=req.symbol)
                return EarningsResponse(
                    symbol=req.symbol, xml_data=cached.xml_data,
                    cached=True, fetched_at=cached.fetched_at,
                )

        contract = self._ibkr.make_contract(
            symbol=req.symbol, sec_type=req.sec_type.value,
            exchange=req.exchange, currency=req.currency,
        )
        xml = await get_earnings_data(self._ibkr, contract)
        response = EarningsResponse(
            symbol=req.symbol, xml_data=xml,
            sec_type=req.sec_type.value, currency=req.currency,
        )
        await self._earn_repo.upsert(response)
        return response
