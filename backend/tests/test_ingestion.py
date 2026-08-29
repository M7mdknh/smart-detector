import uuid

import pytest

from app.contracts.enums import Gas, ReadingQuality, ReadingSource, Unit
from app.contracts.errors import ApiError
from app.contracts.sensor import SensorReadingIn
from app.services import ingestion


def make_reading(**overrides):
    defaults = dict(
        reading_id=uuid.uuid4(),
        sensor_id="co2-sensor-1",
        zone_id="zone-1",
        scenario_id="test-scenario",
        gas=Gas.CO2,
        value=500.0,
        unit=Unit.PPM,
        event_time=__import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc),
        source=ReadingSource.SIMULATOR,
        quality=ReadingQuality.GOOD,
    )
    defaults.update(overrides)
    return SensorReadingIn(**defaults)


def test_ingest_new_reading(session, now):
    reading = make_reading()
    out, is_new = ingestion.ingest_reading(session, reading, now=now)
    assert is_new
    assert out.value == 500.0


def test_duplicate_identical_reading_is_idempotent(session, now):
    rid = uuid.uuid4()
    r1 = make_reading(reading_id=rid)
    out1, is_new1 = ingestion.ingest_reading(session, r1, now=now)
    r2 = make_reading(reading_id=rid)
    out2, is_new2 = ingestion.ingest_reading(session, r2, now=now)
    assert is_new1 is True
    assert is_new2 is False
    assert out1.reading_id == out2.reading_id


def test_duplicate_conflicting_reading_rejected(session, now):
    rid = uuid.uuid4()
    r1 = make_reading(reading_id=rid, value=500.0)
    ingestion.ingest_reading(session, r1, now=now)
    r2 = make_reading(reading_id=rid, value=999.0)
    with pytest.raises(ApiError) as exc:
        ingestion.ingest_reading(session, r2, now=now)
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"
    assert exc.value.status_code == 409


def test_negative_value_rejected():
    with pytest.raises(Exception):
        make_reading(value=-5.0)


def test_naive_event_time_rejected():
    import datetime

    with pytest.raises(Exception):
        make_reading(event_time=datetime.datetime(2026, 1, 1))
