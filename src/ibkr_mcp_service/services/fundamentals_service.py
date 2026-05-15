"""Business logic for fetching and caching fundamental data."""

from datetime import datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ibkr_mcp_service.db.repository import FundamentalsRepository, EarningsRepository
from ibkr_mcp_service.models.domain import (
    FundamentalsRequest, FundamentalsResponse,
    EarningsRequest, EarningsResponse,
)
from ibkr_mcp_service.services.ibkr_client import IBKRClient

log = structlog.get_logger(__name__)


class FundamentalsService:
    """Orchestrates fundamental and earnings data fetching with DB caching."""

    def __init__(self, session: AsyncSession, ibkr: IBKRClient) -> None:
        self._fund_repo = FundamentalsRepository(session)
        self._earn_repo = EarningsRepository(session)
        self._ibkr = ibkr

    async def get_fundamentals(self, req: FundamentalsRequest) -> FundamentalsResponse:
        """Return fundamental data, using the cache when available."""
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
        xml = await self._ibkr.get_fundamental_data(contract, req.report_type)
        response = FundamentalsResponse(
            symbol=req.symbol, report_type=req.report_type, xml_data=xml,
            sec_type=req.sec_type.value, currency=req.currency,
        )
        await self._fund_repo.upsert(response)
        return response

    async def get_earnings(self, req: EarningsRequest) -> EarningsResponse:
        """Return earnings data (CalendarReport), using the cache when available."""
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
        xml = await self._ibkr.get_fundamental_data(contract, "CalendarReport")
        response = EarningsResponse(
            symbol=req.symbol, xml_data=xml,
            sec_type=req.sec_type.value, currency=req.currency,
        )
        await self._earn_repo.upsert(response)
        return response