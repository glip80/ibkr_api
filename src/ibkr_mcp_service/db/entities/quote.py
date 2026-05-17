from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ibkr_mcp_service.db.base import Base


class OHLCVBarORM(Base):
    __tablename__ = "ohlcv_bars"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sec_type: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    bar_size: Mapped[str] = mapped_column(String(20), nullable=False)
    what_to_show: Mapped[str] = mapped_column(String(20), nullable=False)
    adjusted: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    bar_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    wap: Mapped[float | None] = mapped_column(Float)
    bar_count: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "symbol", "sec_type", "currency", "bar_size",
            "what_to_show", "adjusted", "bar_date",
            name="uq_ohlcv_bar",
        ),
    )
