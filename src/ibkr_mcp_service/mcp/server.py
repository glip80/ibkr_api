import json
from typing import Any

import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ibkr_mcp_service.mcp.tools.get_earnings import (
    GET_EARNINGS_TOOL,
    SYNC_SYMBOL_TOOL,
    handle_get_earnings,
    handle_sync_symbol,
)
from ibkr_mcp_service.mcp.tools.get_fundamental import (
    GET_FUNDAMENTALS_TOOL,
)
from ibkr_mcp_service.mcp.tools.get_fundamental import (
    handle as handle_fundamentals,
)
from ibkr_mcp_service.mcp.tools.get_quote import (
    GET_QUOTES_TOOL,
)
from ibkr_mcp_service.mcp.tools.get_quote import (
    handle as handle_quote,
)

log = structlog.get_logger(__name__)

server = Server("ibkr-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        GET_QUOTES_TOOL,
        GET_FUNDAMENTALS_TOOL,
        GET_EARNINGS_TOOL,
        SYNC_SYMBOL_TOOL,
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    handlers = {
        "get_quotes": handle_quote,
        "get_fundamentals": handle_fundamentals,
        "get_earnings": handle_get_earnings,
        "sync_symbol": handle_sync_symbol,
    }

    handler = handlers.get(name)
    if handler is None:
        payload = {"error": f"Unknown tool: {name}"}
    else:
        payload = await handler(arguments)

    return [TextContent(type="text", text=json.dumps(payload, default=str, indent=2))]


async def run_mcp_server() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
