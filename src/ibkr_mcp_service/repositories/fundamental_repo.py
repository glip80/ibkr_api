from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ibkr_mcp_service.db.entities.fundamental import FundamentalsORM
from ibkr_mcp_service.models.fundamental import FundamentalsResponse


class FundamentalsRepository:
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
