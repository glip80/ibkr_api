from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ibkr_mcp_service.db.entities.earnings import EarningsORM
from ibkr_mcp_service.models.earnings import EarningsResponse


class EarningsRepository:
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
