from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ibkr_mcp_service.db.entities.quote import OHLCVBarORM
from ibkr_mcp_service.models.quote import OHLCVBar, QuoteResponse

log = structlog.get_logger(__name__)


class QuoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_bars(
        self, symbol: str, sec_type: str, currency: str,
        bar_size: str, what_to_show: str, adjusted: bool,
    ) -> list[OHLCVBar]:
        stmt = (
            select(OHLCVBarORM)
            .filter_by(
                symbol=symbol, sec_type=sec_type, currency=currency,
                bar_size=bar_size, what_to_show=what_to_show, adjusted=int(adjusted),
            )
            .order_by(OHLCVBarORM.bar_date.asc())
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [
            OHLCVBar(
                date=r.bar_date, open=r.open, high=r.high,
                low=r.low, close=r.close, volume=r.volume,
                wap=r.wap, bar_count=r.bar_count,
            )
            for r in rows
        ]

    async def upsert_bars(self, resp: QuoteResponse) -> int:
        if not resp.bars:
            return 0

        now = datetime.now(UTC)
        rows = [
            {
                "symbol": resp.symbol, "sec_type": resp.sec_type,
                "currency": resp.currency, "bar_size": resp.bar_size,
                "what_to_show": resp.what_to_show, "adjusted": int(resp.adjusted),
                "bar_date": b.date, "open": b.open, "high": b.high,
                "low": b.low, "close": b.close, "volume": b.volume,
                "wap": b.wap, "bar_count": b.bar_count, "fetched_at": now,
            }
            for b in resp.bars
        ]

        stmt = insert(OHLCVBarORM).values(rows)
        update_cols = {
            "open": stmt.excluded.open, "high": stmt.excluded.high,
            "low": stmt.excluded.low, "close": stmt.excluded.close,
            "volume": stmt.excluded.volume, "wap": stmt.excluded.wap,
            "bar_count": stmt.excluded.bar_count, "fetched_at": stmt.excluded.fetched_at,
        }
        upsert_stmt = stmt.on_conflict_do_update(
            constraint="uq_ohlcv_bar",
            set_=update_cols,
        )

        result = await self._session.execute(upsert_stmt)
        await self._session.commit()
        return result.rowcount
