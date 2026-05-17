
import asyncio
import sys

from ibkr_mcp_service.logging_conf import configure_logging
from ibkr_mcp_service.ibkr.client import get_ibkr_client
from ibkr_mcp_service.db.session import get_session_factory
from ibkr_mcp_service.models.earnings import EarningsRequest
from ibkr_mcp_service.models.fundamental import FundamentalsRequest
from ibkr_mcp_service.models.quote import QuoteRequest
from ibkr_mcp_service.services.earnings_service import EarningsService
from ibkr_mcp_service.services.fundamentals_service import FundamentalsService
from ibkr_mcp_service.services.quote_service import QuoteService


async def sync_symbols(symbols: list[str]) -> None:
    configure_logging()
    ibkr = get_ibkr_client()
    await ibkr.connect()

    factory = get_session_factory()
    try:
        for symbol in symbols:
            async with factory() as session:
                quotes_svc = QuoteService(session, ibkr)
                fund_svc = FundamentalsService(session, ibkr)
                earn_svc = EarningsService(session, ibkr)

                await quotes_svc.get_quotes(QuoteRequest(symbol=symbol), force_refresh=True)
                await fund_svc.get_fundamentals(FundamentalsRequest(symbol=symbol), force_refresh=True)
                await earn_svc.get_earnings(EarningsRequest(symbol=symbol), force_refresh=True)
                print(f"Synced: {symbol}")
    finally:
        await ibkr.disconnect()


if __name__ == "__main__":
    symbols = sys.argv[1:] or ["AAPL"]
    asyncio.run(sync_symbols(symbols))
