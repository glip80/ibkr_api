from datetime import datetime

from pydantic import BaseModel, field_validator

from ibkr_mcp_service.models.quote import SecType


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
    fetched_at: datetime | None = None
