"""Background sync process – periodically refreshes cached data from IBKR."""

import asyncio
from datetime import datetime

import structlog
from sqlalchemy import select

from ibkr_mcp_service.config import get_settings
from ibkr_mcp_service.db.base import get_session_factory
from ibkr_mcp_service.db.orm_models import OHLCVBarORM
from ibkr_mcp_service.models.domain import (
    QuoteRequest, BarSize, WhatToShow, SecType,
)
from ibkr_mcp_service.services.ibkr_client import get_ibkr_client
from ibkr_mcp_service.services.quote_service import QuoteService

log = structlog.get_logger(__name__)


class SyncManager:
    """Discovers all symbols in the DB and refreshes their data periodically."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._running = False

    async def run_forever(self) -> None:
        """Entry point for the background sync loop."""
        self._running = True
        log.info("sync_manager_started", interval=self._settings.sync_interval_seconds)
        while self._running:
            try:
                await self._sync_all()
            except Exception:
                log.exception("sync_cycle_failed")
            await asyncio.sleep(self._settings.sync_interval_seconds)

    def stop(self) -> None:
        """Signal the sync loop to stop after the current cycle."""
        self._running = False

    async def _sync_all(self) -> None:
        """Run one full sync cycle over all known symbols."""
        log.info("sync_cycle_started")
        factory = get_session_factory()
        ibkr = get_ibkr_client()

        # Collect distinct symbol combos from ohlcv_bars
        session = factory()
        try:
            result = await session.execute(
                select(
                    OHLCVBarORM.symbol,
                    OHLCVBarORM.sec_type,
                    OHLCVBarORM.currency,
                    OHLCVBarORM.bar_size,
                    OHLCVBarORM.what_to_show,
                    OHLCVBarORM.adjusted,
                ).distinct()
            )
            quote_keys = result.fetchall()
        finally:
            await session.close()

        for row in quote_keys:
            try:
                req = QuoteRequest(
                    symbol=row.symbol,
                    sec_type=SecType(row.sec_type),
                    currency=row.currency,
                    bar_size=BarSize(row.bar_size),
                    what_to_show=WhatToShow(row.what_to_show),
                    adjusted=bool(row.adjusted),
                    duration=f"{self._settings.sync_lookback_days} D",
                )
                session = factory()
                try:
                    svc = QuoteService(session, ibkr)
                    resp = await svc.get_quotes(req)
                    log.info("sync_refreshed_quote", symbol=req.symbol, bars=len(resp.bars))
                finally:
                    await session.close()
            except Exception:
                log.exception("sync_failed_for_symbol", symbol=row.symbol)

        log.info("sync_cycle_completed", symbols_processed=len(quote_keys))