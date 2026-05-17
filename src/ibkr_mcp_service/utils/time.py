"""Time and date helpers for IBKR integration."""

import re
from datetime import UTC, datetime, timedelta

_DURATION_RE = re.compile(
    r"^\s*(?P<value>\d+)\s*(?P<unit>[YMWDSH])\s*$",
)


def utc_now() -> datetime:
    """Current UTC datetime without fractional seconds."""
    return datetime.now(UTC).replace(microsecond=0)


def parse_ibkr_duration(duration_str: str) -> timedelta | None:
    """Convert an IBKR duration string (e.g. '1 Y', '30 D', '6 M') to a timedelta.

    Supported units: S (seconds), H (hours), D (days), W (weeks), M (months), Y (years).
    Returns ``None`` when the string cannot be parsed.
    """
    m = _DURATION_RE.match(duration_str.strip().upper() if duration_str else "")
    if not m:
        return None

    value = int(m.group("value"))
    unit = m.group("unit")

    if unit == "S":
        return timedelta(seconds=value)
    if unit == "H":
        return timedelta(hours=value)
    if unit == "D":
        return timedelta(days=value)
    if unit == "W":
        return timedelta(weeks=value)
    if unit == "M":
        return timedelta(days=value * 30)
    # unit == "Y" — guaranteed by regex
    return timedelta(days=value * 365)


def lookback_start(days: int) -> datetime:
    """Return the UTC datetime `days` ago (midnight-aligned)."""
    return utc_now().replace(hour=0, minute=0, second=0) - timedelta(days=days)
