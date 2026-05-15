"""MCP tool definitions – the public interface of the service."""

import json
from typing import Any

import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ibkr_mcp_service.db.base import get_session_factory
from ibkr_mcp_service.models.domain import (
    BarSize,
    EarningsRequest,
    FundamentalsRequest,
    QuoteRequest,
    SecType,
    WhatToShow,
)
from ibkr_mcp_service.services.fundamentals_service import FundamentalsService
from ibkr_mcp_service.services.ibkr_client import get_ibkr_client
from ibkr_mcp_service.services.quote_service import QuoteService

log = structlog.get_logger(__name__)

server = Server("ibkr-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Advertise available MCP tools to callers."""
    return [
        Tool(
            name="get_quotes",
            description=(
                "Fetch historical OHLCV bars for a symbol from IBKR. "
                "Results are persisted and served from cache on subsequent calls."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker, e.g. AAPL"},
                    "sec_type": {
                        "type": "string",
                        "enum": [e.value for e in SecType],
                        "default": "STK",
                    },
                    "exchange": {"type": "string", "default": "SMART"},
                    "currency": {"type": "string", "default": "USD"},
                    "duration": {
                        "type": "string",
                        "default": "1 Y",
                        "description": "IBKR duration string, e.g. '30 D', '6 M', '1 Y'",
                    },
                    "bar_size": {
                        "type": "string",
                        "enum": [e.value for e in BarSize],
                        "default": "1 day",
                    },
                    "what_to_show": {
                        "type": "string",
                        "enum": [e.value for e in WhatToShow],
                        "default": "TRADES",
                    },
                    "use_rth": {"type": "boolean", "default": True},
                    "adjusted": {"type": "boolean", "default": True},
                    "end_datetime": {
                        "type": "string",
                        "default": "",
                        "description": "End datetime; empty = now",
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="get_fundamentals",
            description=(
                "Retrieve IBKR fundamental data XML for a symbol. "
                "Cached in PostgreSQL after the first request."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "sec_type": {"type": "string", "default": "STK"},
                    "exchange": {"type": "string", "default": "SMART"},
                    "currency": {"type": "string", "default": "USD"},
                    "report_type": {
                        "type": "string",
                        "default": "ReportsFinSummary",
                        "enum": [
                            "ReportsFinSummary", "ReportSnapshot",
                            "ReportsOwnership", "ReportRatios",
                            "CalendarReport", "RESC",
                        ],
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="get_earnings",
            description=(
                "Retrieve IBKR earnings/calendar data for a symbol. "
                "Cached in PostgreSQL after the first request."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "sec_type": {"type": "string", "default": "STK"},
                    "exchange": {"type": "string", "default": "SMART"},
                    "currency": {"type": "string", "default": "USD"},
                },
                "required": ["symbol"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Route MCP tool calls to the appropriate service."""
    factory = get_session_factory()
    ibkr = get_ibkr_client()

    async with factory() as session:
        if name == "get_quotes":
            req = QuoteRequest(**arguments)
            svc = QuoteService(session, ibkr)
            result = await svc.get_quotes(req)
            payload = result.model_dump(mode="json")

        elif name == "get_fundamentals":
            req = FundamentalsRequest(**arguments)
            svc = FundamentalsService(session, ibkr)
            result = await svc.get_fundamentals(req)
            payload = result.model_dump(mode="json")

        elif name == "get_earnings":
            req = EarningsRequest(**arguments)
            svc = FundamentalsService(session, ibkr)
            result = await svc.get_earnings(req)
            payload = result.model_dump(mode="json")

        else:
            payload = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(payload, default=str, indent=2))]


async def run_mcp_server() -> None:
    """Start the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())