"""Two clocks: wall clock (ingested_at) and simulation event clock (event_time).

Tests inject a FakeClock instead of sleeping.
"""

from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class WallClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """SQLite loses tzinfo on round-trip; normalize naive datetimes back to UTC-aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class FakeClock:
    def __init__(self, start: datetime):
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._now = self._now + timedelta(seconds=seconds)

    def set(self, t: datetime) -> None:
        self._now = t
