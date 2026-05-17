"""Unit tests for Pydantic domain models."""

import pytest
from pydantic import ValidationError

from ibkr_mcp_service.models.earnings import EarningsRequest
from ibkr_mcp_service.models.fundamental import FundamentalsRequest
from ibkr_mcp_service.models.quote import BarSize, QuoteRequest, SecType, WhatToShow


def test_quote_request_defaults():
    req = QuoteRequest(symbol="aapl")
    assert req.symbol == "AAPL"           # normalised to upper
    assert req.sec_type == SecType.STK
    assert req.bar_size == BarSize.D1
    assert req.what_to_show == WhatToShow.TRADES
    assert req.use_rth is True
    assert req.adjusted is True
    assert req.duration == "1 Y"
    assert req.end_datetime == ""


def test_quote_request_custom_values():
    req = QuoteRequest(
        symbol="eurusd",
        sec_type="CASH",
        exchange="IDEALPRO",
        currency="EUR",
        duration="30 D",
        bar_size="1 hour",
        what_to_show="MIDPOINT",
        use_rth=False,
        adjusted=False,
    )
    assert req.symbol == "EURUSD"
    assert req.sec_type == SecType.CASH
    assert req.bar_size == BarSize.H1
    assert req.use_rth is False


def test_quote_request_invalid_bar_size():
    with pytest.raises(ValidationError):
        QuoteRequest(symbol="AAPL", bar_size="99 years")


def test_fundamentals_request_defaults():
    req = FundamentalsRequest(symbol="msft")
    assert req.symbol == "MSFT"
    assert req.report_type == "ReportsFinSummary"


def test_earnings_request_normalises_symbol():
    req = EarningsRequest(symbol=" tsla ")
    assert req.symbol == "TSLA"