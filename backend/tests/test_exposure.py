from datetime import datetime, timedelta, timezone

from app.domain.exposure.rolling import TimedValue, rolling_short_term, rolling_twa


def test_time_weighted_average_irregular_spacing():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    readings = [
        TimedValue(base, 400.0),
        TimedValue(base + timedelta(minutes=5), 600.0),
        TimedValue(base + timedelta(minutes=15), 400.0),  # held for 10 minutes
    ]
    now = base + timedelta(minutes=15)
    avg = rolling_short_term(readings, now)
    # segment1: 400 held 5 min, segment2: 600 held 10 min -> weighted avg
    expected = (400 * 5 + 600 * 10) / 15
    assert avg is not None
    assert abs(avg - expected) < 1e-6


def test_partial_window_flagged():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    readings = [TimedValue(base, 500.0), TimedValue(base + timedelta(hours=1), 500.0)]
    now = base + timedelta(hours=1)
    twa, partial = rolling_twa(readings, now)
    assert partial is True
    assert twa is not None


def test_full_eight_hour_window_not_partial():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    readings = [TimedValue(base + timedelta(minutes=5 * i), 500.0) for i in range(97)]  # 8 hours at 5-min cadence
    now = base + timedelta(hours=8)
    twa, partial = rolling_twa(readings, now)
    assert partial is False
    assert twa == 500.0


def test_no_data_returns_none():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    avg = rolling_short_term([], now)
    assert avg is None
