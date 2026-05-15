"""Background sync process – periodically refreshes cached data from IBKR."""

import asyncio
from collections.abc import Sequence
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibkr_mcp_service.config import get_settings
from ibkr_mcp_service.db.base import get_session_factory
from ibkr_mcp_service.db.orm_models import EarningsORM, FundamentalsORM, OHLCVBarORM
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


class SyncManager:
    """Discovers all known symbols across every data table and refreshes
    their data from IBKR periodically, bypassing the read cache."""

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
        """Run one full sync cycle over all known symbols and data types."""
        log.info("sync_cycle_started")
        factory = get_session_factory()
        ibkr = get_ibkr_client()

        session = factory()
        try:
            ohlcv_keys = await self._get_ohlcv_keys(session)
            fund_keys = await self._get_fundamentals_keys(session)
            earn_symbols = await self._get_earnings_symbols(session)
        finally:
            await session.close()

        # ── Sync OHLCV bars ──────────────────────────────────────────────
        for row in ohlcv_keys:
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
                    resp = await svc.get_quotes(req, force_refresh=True)
                    log.info(
                        "sync_refreshed_quotes",
                        symbol=req.symbol,
                        bars=len(resp.bars),
                    )
                finally:
                    await session.close()
            except Exception:
                log.exception("sync_quotes_failed", symbol=row.symbol)

        # ── Sync fundamentals ────────────────────────────────────────────
        for row in fund_keys:
            try:
                req = FundamentalsRequest(
                    symbol=row.symbol,
                    sec_type=SecType(row.sec_type),
                    currency=row.currency,
                    report_type=row.report_type,
                )
                session = factory()
                try:
                    svc = FundamentalsService(session, ibkr)
                    resp = await svc.get_fundamentals(req, force_refresh=True)
                    log.info(
                        "sync_refreshed_fundamentals",
                        symbol=req.symbol,
                        report_type=req.report_type,
                    )
                finally:
                    await session.close()
            except Exception:
                log.exception("sync_fundamentals_failed", symbol=row.symbol)

        # ── Sync earnings ───────────────────────────────────────────────
        for row in earn_symbols:
            try:
                req = EarningsRequest(
                    symbol=row.symbol,
                    sec_type=SecType(row.sec_type),
                    currency=row.currency,
                )
                session = factory()
                try:
                    svc = FundamentalsService(session, ibkr)
                    resp = await svc.get_earnings(req, force_refresh=True)
                    log.info(
                        "sync_refreshed_earnings",
                        symbol=req.symbol,
                    )
                finally:
                    await session.close()
            except Exception:
                log.exception("sync_earnings_failed", symbol=row.symbol)

        log.info(
            "sync_cycle_completed",
            ohlcv_count=len(ohlcv_keys),
            fundamentals_count=len(fund_keys),
            earnings_count=len(earn_symbols),
        )

    async def _get_ohlcv_keys(self, session: AsyncSession) -> Sequence[Any]:
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
        return result.fetchall()  # type: ignore[no-any-return]

    async def _get_fundamentals_keys(self, session: AsyncSession) -> Sequence[Any]:
        result = await session.execute(
            select(
                FundamentalsORM.symbol,
                FundamentalsORM.sec_type,
                FundamentalsORM.currency,
                FundamentalsORM.report_type,
            ).distinct()
        )
        return result.fetchall()  # type: ignore[no-any-return]

    async def _get_earnings_symbols(self, session: AsyncSession) -> Sequence[Any]:
        result = await session.execute(
            select(
                EarningsORM.symbol,
                EarningsORM.sec_type,
                EarningsORM.currency,
            ).distinct()
        )
        return result.fetchall()  # type: ignore[no-any-return]
