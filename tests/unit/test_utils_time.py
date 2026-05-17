from datetime import UTC, datetime, timedelta

import pytest

from ibkr_mcp_service.utils.time import lookback_start, parse_ibkr_duration, utc_now


def test_utc_now_returns_datetime():
    result = utc_now()
    assert isinstance(result, datetime)
    assert result.tzinfo == UTC
    assert result.microsecond == 0


def test_utc_now_is_recent():
    result = utc_now()
    delta = datetime.now(UTC) - result
    assert abs(delta.total_seconds()) < 5


def test_parse_ibkr_duration_seconds():
    assert parse_ibkr_duration("30 S") == timedelta(seconds=30)


def test_parse_ibkr_duration_hours():
    assert parse_ibkr_duration("2 H") == timedelta(hours=2)


def test_parse_ibkr_duration_days():
    assert parse_ibkr_duration("10 D") == timedelta(days=10)


def test_parse_ibkr_duration_weeks():
    assert parse_ibkr_duration("3 W") == timedelta(weeks=3)


def test_parse_ibkr_duration_months():
    assert parse_ibkr_duration("6 M") == timedelta(days=180)


def test_parse_ibkr_duration_years():
    assert parse_ibkr_duration("1 Y") == timedelta(days=365)


def test_parse_ibkr_duration_lowercase():
    assert parse_ibkr_duration("5 d") == timedelta(days=5)


def test_parse_ibkr_duration_extra_whitespace():
    assert parse_ibkr_duration("  7  D  ") == timedelta(days=7)


def test_parse_ibkr_duration_invalid_returns_none():
    assert parse_ibkr_duration("abc") is None
    assert parse_ibkr_duration("") is None
    assert parse_ibkr_duration("12X") is None


def test_parse_ibkr_duration_none_returns_none():
    assert parse_ibkr_duration(None) is None  # type: ignore[arg-type]


def test_lookback_start_returns_midnight_utc():
    result = lookback_start(7)
    assert isinstance(result, datetime)
    assert result.tzinfo == UTC
    assert result.hour == 0
    assert result.minute == 0
    assert result.second == 0
    assert result.microsecond == 0


def test_lookback_start_is_approx_days_ago():
    result = lookback_start(30)
    expected = (datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
                - timedelta(days=30))
    delta = abs((result - expected).total_seconds())
    assert delta < 5
