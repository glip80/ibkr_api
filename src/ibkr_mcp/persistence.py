"""
SQLite-backed persistence layer.

Stores:
  - ``quotes``       — OHLCV bars keyed by (symbol, bar_size, what_to_show, date)
  - ``fundamentals`` — raw XML keyed by (symbol, report_type, fetched_at)
  - ``earnings``     — raw XML (RESC report) keyed by (symbol, fetched_at)
  - ``sync_log``     — record of background sync runs

Design choices
--------------
* aiosqlite for non-blocking I/O inside asyncio event loop.
* All writes are upserts (INSERT OR REPLACE) so re-fetching is idempotent.
* TTL checks are done at read time — stale rows are returned with a flag,
  not deleted, so callers can decide whether to re-fetch.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS quotes (
    symbol          TEXT    NOT NULL,
    bar_size        TEXT    NOT NULL,
    what_to_show    TEXT    NOT NULL,
    date            TEXT    NOT NULL,
    open            REAL,
    high            REAL,
    low             REAL,
    close           REAL,
    volume          REAL,
    average         REAL,
    bar_count       INTEGER,
    fetched_at      TEXT    NOT NULL,
    PRIMARY KEY (symbol, bar_size, what_to_show, date)
);

CREATE TABLE IF NOT EXISTS fundamentals (
    symbol          TEXT    NOT NULL,
    report_type     TEXT    NOT NULL,
    xml_data        TEXT    NOT NULL,
    fetched_at      TEXT    NOT NULL,
    PRIMARY KEY (symbol, report_type)
);

CREATE TABLE IF NOT EXISTS earnings (
    symbol          TEXT    NOT NULL,
    xml_data        TEXT    NOT NULL,
    fetched_at      TEXT    NOT NULL,
    PRIMARY KEY (symbol)
);

CREATE TABLE IF NOT EXISTS sync_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    data_type       TEXT    NOT NULL,   -- 'quotes' | 'fundamentals' | 'earnings'
    status          TEXT    NOT NULL,   -- 'ok' | 'error'
    message         TEXT,
    started_at      TEXT    NOT NULL,
    finished_at     TEXT
);
"""

_DEFAULT_DB_PATH = Path("data/ibkr_cache.db")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class PersistenceStore:
    """Async SQLite wrapper for caching IBKR market data.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file (created on first use).
    quotes_ttl_hours:
        How many hours before a quotes cache entry is considered stale.
    fundamentals_ttl_hours:
        TTL for fundamental / earnings XML data.
    """

    def __init__(
        self,
        db_path: Path = _DEFAULT_DB_PATH,
        quotes_ttl_hours: int = 1,
        fundamentals_ttl_hours: int = 24,
    ) -> None:
        self.db_path = db_path
        self.quotes_ttl = timedelta(hours=quotes_ttl_hours)
        self.fundamentals_ttl = timedelta(hours=fundamentals_ttl_hours)
        self._db_path_str = str(db_path)

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def init(self) -> None:
        """Create the database file and apply schema migrations."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path_str) as db:
            await db.executescript(_SCHEMA)
            await db.commit()
        logger.info("Database initialised at %s", self.db_path)

    # ── quotes ───────────────────────────────────────────────────────────────

    async def upsert_quotes(
        self,
        symbol: str,
        bar_size: str,
        what_to_show: str,
        bars: list[dict[str, Any]],
    ) -> None:
        """Insert or replace OHLCV bars."""
        now = _utcnow()
        rows = [
            (
                symbol.upper(), bar_size, what_to_show,
                b["date"], b["open"], b["high"], b["low"], b["close"],
                b["volume"], b["average"], b["bar_count"], now,
            )
            for b in bars
        ]
        async with aiosqlite.connect(self._db_path_str) as db:
            await db.executemany(
                """INSERT OR REPLACE INTO quotes
                   (symbol, bar_size, what_to_show, date, open, high, low, close,
                    volume, average, bar_count, fetched_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                rows,
            )
            await db.commit()
        logger.debug("Upserted %d bars for %s (%s)", len(rows), symbol, bar_size)

    async def get_quotes(
        self,
        symbol: str,
        bar_size: str,
        what_to_show: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Read cached OHLCV bars.

        Returns
        -------
        tuple[list[dict], bool]
            The cached bars (may be empty) and a boolean ``is_stale``
            that is ``True`` when the most-recent ``fetched_at`` timestamp
            exceeds :attr:`quotes_ttl`.
        """
        query = """
            SELECT date, open, high, low, close, volume, average, bar_count, fetched_at
            FROM quotes
            WHERE symbol=? AND bar_size=? AND what_to_show=?
        """
        params: list[Any] = [symbol.upper(), bar_size, what_to_show]
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date ASC"

        async with aiosqlite.connect(self._db_path_str) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return [], True  # No data → treat as stale

        bars = [dict(r) for r in rows]
        latest_fetch = max(r["fetched_at"] for r in bars)
        fetched_dt = datetime.fromisoformat(latest_fetch)
        is_stale = (datetime.now(timezone.utc) - fetched_dt) > self.quotes_ttl
        return bars, is_stale

    # ── fundamentals ─────────────────────────────────────────────────────────

    async def upsert_fundamentals(self, symbol: str, report_type: str, xml_data: str) -> None:
        """Store fundamental XML, replacing any previous entry."""
        async with aiosqlite.connect(self._db_path_str) as db:
            await db.execute(
                "INSERT OR REPLACE INTO fundamentals (symbol, report_type, xml_data, fetched_at) VALUES (?,?,?,?)",
                (symbol.upper(), report_type, xml_data, _utcnow()),
            )
            await db.commit()
        logger.debug("Upserted fundamentals for %s (%s)", symbol, report_type)

    async def get_fundamentals(
        self, symbol: str, report_type: str
    ) -> tuple[str | None, bool]:
        """Return (xml_data, is_stale) for *symbol* / *report_type*."""
        async with aiosqlite.connect(self._db_path_str) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT xml_data, fetched_at FROM fundamentals WHERE symbol=? AND report_type=?",
                (symbol.upper(), report_type),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None, True
        fetched_dt = datetime.fromisoformat(row["fetched_at"])
        is_stale = (datetime.now(timezone.utc) - fetched_dt) > self.fundamentals_ttl
        return row["xml_data"], is_stale

    # ── earnings ─────────────────────────────────────────────────────────────

    async def upsert_earnings(self, symbol: str, xml_data: str) -> None:
        """Store earnings XML (RESC report)."""
        async with aiosqlite.connect(self._db_path_str) as db:
            await db.execute(
                "INSERT OR REPLACE INTO earnings (symbol, xml_data, fetched_at) VALUES (?,?,?)",
                (symbol.upper(), xml_data, _utcnow()),
            )
            await db.commit()
        logger.debug("Upserted earnings for %s", symbol)

    async def get_earnings(self, symbol: str) -> tuple[str | None, bool]:
        """Return (xml_data, is_stale) for earnings data."""
        async with aiosqlite.connect(self._db_path_str) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT xml_data, fetched_at FROM earnings WHERE symbol=?",
                (symbol.upper(),),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None, True
        fetched_dt = datetime.fromisoformat(row["fetched_at"])
        is_stale = (datetime.now(timezone.utc) - fetched_dt) > self.fundamentals_ttl
        return row["xml_data"], is_stale

    # ── sync log ─────────────────────────────────────────────────────────────

    async def log_sync(
        self,
        symbol: str,
        data_type: str,
        status: str,
        message: str | None,
        started_at: str,
        finished_at: str | None = None,
    ) -> None:
        """Append a row to the sync_log table."""
        async with aiosqlite.connect(self._db_path_str) as db:
            await db.execute(
                """INSERT INTO sync_log (symbol, data_type, status, message, started_at, finished_at)
                   VALUES (?,?,?,?,?,?)""",
                (symbol.upper(), data_type, status, message, started_at, finished_at or _utcnow()),
            )
            await db.commit()

    async def get_sync_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return the most recent *limit* sync log entries."""
        async with aiosqlite.connect(self._db_path_str) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sync_log ORDER BY id DESC LIMIT ?", (limit,)
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]
