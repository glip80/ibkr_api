from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, field_validator


class SecType(StrEnum):
    STK = "STK"
    OPT = "OPT"
    FUT = "FUT"
    IND = "IND"
    FOP = "FOP"
    CASH = "CASH"
    BAG = "BAG"
    WAR = "WAR"


class BarSize(StrEnum):
    S1 = "1 sec"
    S5 = "5 secs"
    S15 = "15 secs"
    S30 = "30 secs"
    M1 = "1 min"
    M2 = "2 mins"
    M3 = "3 mins"
    M5 = "5 mins"
    M15 = "15 mins"
    M30 = "30 mins"
    H1 = "1 hour"
    H2 = "2 hours"
    H3 = "3 hours"
    H4 = "4 hours"
    H8 = "8 hours"
    D1 = "1 day"
    W1 = "1 week"
    MON1 = "1 month"


class WhatToShow(StrEnum):
    TRADES = "TRADES"
    MIDPOINT = "MIDPOINT"
    BID = "BID"
    ASK = "ASK"
    BID_ASK = "BID_ASK"
    HISTORICAL_VOLATILITY = "HISTORICAL_VOLATILITY"
    OPTION_IMPLIED_VOLATILITY = "OPTION_IMPLIED_VOLATILITY"
    YIELD_ASK = "YIELD_ASK"
    YIELD_BID = "YIELD_BID"
    YIELD_BID_ASK = "YIELD_BID_ASK"
    YIELD_LAST = "YIELD_LAST"


class QuoteRequest(BaseModel):
    symbol: str
    sec_type: SecType = SecType.STK
    exchange: str = "SMART"
    currency: str = "USD"
    duration: str = "1 Y"
    bar_size: BarSize = BarSize.D1
    what_to_show: WhatToShow = WhatToShow.TRADES
    use_rth: bool = True
    adjusted: bool = True
    end_datetime: str = ""

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        return v.strip().upper()


class OHLCVBar(BaseModel):
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    wap: float | None = None
    bar_count: int | None = None


class QuoteResponse(BaseModel):
    symbol: str
    sec_type: str
    currency: str
    bar_size: str
    what_to_show: str
    adjusted: bool
    bars: list[OHLCVBar]
    cached: bool = False
    fetched_at: datetime | None = None
