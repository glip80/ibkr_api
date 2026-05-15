"""Business logic for historical market data fetching and caching."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ibkr_mcp_service.db.repository import QuoteRepository
from ibkr_mcp_service.models.domain import (
    OHLCVBar,
    QuoteRequest,
    QuoteResponse,
)
from ibkr_mcp_service.services.ibkr_client import IBKRClient

log = structlog.get_logger(__name__)


class QuoteService:
    """Orchestrates historical quote fetching with a cache-first strategy."""

    def __init__(self, session: AsyncSession, ibkr: IBKRClient) -> None:
        self._repo = QuoteRepository(session)
        self._ibkr = ibkr

    async def get_quotes(self, req: QuoteRequest, force_refresh: bool = False) -> QuoteResponse:
        """Return quotes from cache if available, otherwise fetch from IBKR.

        When *force_refresh* is ``True`` the cache is skipped and fresh data
        is always fetched from IBKR (the result is still persisted).
        """
        if not force_refresh:
            cached_bars = await self._repo.get_bars(
                symbol=req.symbol, sec_type=req.sec_type.value,
                currency=req.currency, bar_size=req.bar_size.value,
                what_to_show=req.what_to_show.value, adjusted=req.adjusted,
            )

            if cached_bars:
                log.info("cache_hit_quotes", symbol=req.symbol, count=len(cached_bars))
                return QuoteResponse(
                    symbol=req.symbol, sec_type=req.sec_type.value,
                    currency=req.currency, bar_size=req.bar_size.value,
                    what_to_show=req.what_to_show.value, adjusted=req.adjusted,
                    bars=cached_bars, cached=True,
                )

        # Cache miss – fetch from live API
        contract = self._ibkr.make_contract(
            symbol=req.symbol, sec_type=req.sec_type.value,
            currency=req.currency,
        )
        raw_bars = await self._ibkr.get_historical_data(
            contract=contract,
            end_datetime=req.end_datetime,
            duration_str=req.duration,
            bar_size_setting=req.bar_size.value,
            what_to_show=req.what_to_show.value,
            use_rth=req.use_rth,
        )

        domain_bars = [
            OHLCVBar(
                date=b.date, open=b.open, high=b.high,
                low=b.low, close=b.close, volume=b.volume,
                wap=b.wap, bar_count=b.barCount,
            )
            for b in raw_bars
        ]

        response = QuoteResponse(
            symbol=req.symbol, sec_type=req.sec_type.value,
            currency=req.currency, bar_size=req.bar_size.value,
            what_to_show=req.what_to_show.value, adjusted=req.adjusted,
            bars=domain_bars, cached=False,
        )

        # Persist to database
        await self._repo.upsert_bars(response)
        return response
