"""Rolling exposure calculations: short-term (15 min) and TWA (8 hr).

Uses time-weighted averaging over irregular event times (trapezoid-of-holds:
each reading's value is held constant until the next reading, matching sensor
cadence semantics rather than assuming uniform sampling).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class TimedValue:
    event_time: datetime
    value: float


def time_weighted_average(readings: list[TimedValue], window_end: datetime, window: timedelta) -> tuple[float | None, bool]:
    """Returns (twa_value, partial_window). None if no data in window."""
    window_start = window_end - window
    in_window = [r for r in readings if window_start <= r.event_time <= window_end]
    if not in_window:
        return None, True

    in_window = sorted(in_window, key=lambda r: r.event_time)
    partial = in_window[0].event_time > window_start + timedelta(seconds=1)

    total_weight = 0.0
    weighted_sum = 0.0
    for i, r in enumerate(in_window):
        seg_start = r.event_time
        seg_end = in_window[i + 1].event_time if i + 1 < len(in_window) else window_end
        dt = max(0.0, (seg_end - seg_start).total_seconds())
        weighted_sum += r.value * dt
        total_weight += dt

    if total_weight <= 0:
        return in_window[-1].value, partial

    return weighted_sum / total_weight, partial


def rolling_short_term(readings: list[TimedValue], now: datetime) -> float | None:
    val, _ = time_weighted_average(readings, now, timedelta(minutes=15))
    return val


def rolling_twa(readings: list[TimedValue], now: datetime) -> tuple[float | None, bool]:
    return time_weighted_average(readings, now, timedelta(hours=8))
