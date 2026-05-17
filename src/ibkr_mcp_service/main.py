"""Application entry point – starts the MCP server and background sync."""

import asyncio

import structlog

from ibkr_mcp_service.ibkr.client import get_ibkr_client
from ibkr_mcp_service.logging_conf import configure_logging
from ibkr_mcp_service.mcp.server import run_mcp_server
from ibkr_mcp_service.services.sync_service import SyncService

log = structlog.get_logger(__name__)


async def _startup() -> None:
    """Connect to IBKR and start background sync before serving MCP requests."""
    client = get_ibkr_client()
    await client.connect()


async def _async_main() -> None:
    configure_logging()
    await _startup()

    sync_service = SyncService()
    sync_task = asyncio.create_task(sync_service.run_forever())

    try:
        await run_mcp_server()
    finally:
        sync_service.stop()
        sync_task.cancel()
        await get_ibkr_client().disconnect()


def main() -> None:
    """Synchronous entry point wired up by pyproject.toml."""
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()