"""Pydantic models for the IBKR MCP service domain."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class SecType(str, Enum):
    STK = "STK"
    OPT = "OPT"
    FUT = "FUT"
    IND = "IND"
    FOP = "FOP"
    CASH = "CASH"
    BAG = "BAG"
    WAR = "WAR"


class BarSize(str, Enum):
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


class WhatToShow(str, Enum):
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
    wap: Optional[float] = None
    bar_count: Optional[int] = None


class QuoteResponse(BaseModel):
    symbol: str
    sec_type: str
    currency: str
    bar_size: str
    what_to_show: str
    adjusted: bool
    bars: list[OHLCVBar]
    cached: bool = False
    fetched_at: Optional[datetime] = None


class FundamentalsRequest(BaseModel):
    symbol: str
    sec_type: SecType = SecType.STK
    exchange: str = "SMART"
    currency: str = "USD"
    report_type: str = "ReportsFinSummary"

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        return v.strip().upper()


class FundamentalsResponse(BaseModel):
    symbol: str
    report_type: str
    xml_data: str
    sec_type: str = "STK"
    currency: str = "USD"
    cached: bool = False
    fetched_at: Optional[datetime] = None


class EarningsRequest(BaseModel):
    symbol: str
    sec_type: SecType = SecType.STK
    exchange: str = "SMART"
    currency: str = "USD"

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        return v.strip().upper()


class EarningsResponse(BaseModel):
    symbol: str
    xml_data: str
    sec_type: str = "STK"
    currency: str = "USD"
    cached: bool = False
    fetched_at: Optional[datetime] = None
