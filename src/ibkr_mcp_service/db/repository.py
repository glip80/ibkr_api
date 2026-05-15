"""Data Access Layer for the IBKR MCP service."""

from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ibkr_mcp_service.db.orm_models import EarningsORM, FundamentalsORM, OHLCVBarORM
from ibkr_mcp_service.models.domain import (
    EarningsResponse,
    FundamentalsResponse,
    OHLCVBar,
    QuoteResponse,
)

log = structlog.get_logger(__name__)


class QuoteRepository:
    """Handles persistence for OHLCV bars."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_bars(
        self, symbol: str, sec_type: str, currency: str,
        bar_size: str, what_to_show: str, adjusted: bool,
    ) -> list[OHLCVBar]:
        """Fetch cached bars from the database."""
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
        """Insert or update bars in bulk using PostgreSQL upsert."""
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


class FundamentalsRepository:
    """Handles persistence for fundamental XML data."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, symbol: str, report_type: str) -> FundamentalsORM | None:
        stmt = select(FundamentalsORM).filter_by(symbol=symbol, report_type=report_type)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, resp: FundamentalsResponse) -> None:
        now = datetime.now(UTC)
        stmt = insert(FundamentalsORM).values(
            symbol=resp.symbol, report_type=resp.report_type,
            xml_data=resp.xml_data, fetched_at=now,
            sec_type=resp.sec_type, currency=resp.currency,
        )
        upsert_stmt = stmt.on_conflict_do_update(
            constraint="uq_fundamentals",
            set_={"xml_data": stmt.excluded.xml_data, "fetched_at": stmt.excluded.fetched_at},
        )
        await self._session.execute(upsert_stmt)
        await self._session.commit()


class EarningsRepository:
    """Handles persistence for earnings XML data."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, symbol: str) -> EarningsORM | None:
        stmt = select(EarningsORM).filter_by(symbol=symbol)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, resp: EarningsResponse) -> None:
        now = datetime.now(UTC)
        stmt = insert(EarningsORM).values(
            symbol=resp.symbol, xml_data=resp.xml_data, fetched_at=now,
            sec_type=resp.sec_type, currency=resp.currency,
        )
        upsert_stmt = stmt.on_conflict_do_update(
            constraint="uq_earnings_symbol",
            set_={"xml_data": stmt.excluded.xml_data, "fetched_at": stmt.excluded.fetched_at},
        )
        await self._session.execute(upsert_stmt)
        await self._session.commit()
