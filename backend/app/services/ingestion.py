"""Public ingestion path. Simulator, replay, and future devices all call this.

Idempotent by reading_id: identical duplicate returns the original outcome;
conflicting duplicate raises ApiError(IDEMPOTENCY_CONFLICT).
"""

import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.contracts.errors import ApiError
from app.contracts.sensor import SensorReadingIn, SensorReadingOut
from app.storage.models import SensorReadingRow


def _payload_hash(reading: SensorReadingIn) -> str:
    raw = reading.model_dump_json(exclude={"reading_id"})
    return hashlib.sha256(raw.encode()).hexdigest()


def ingest_reading(session: Session, reading: SensorReadingIn, now: datetime | None = None) -> tuple[SensorReadingOut, bool]:
    """Returns (reading_out, is_new)."""
    now = now or datetime.now(timezone.utc)
    reading_id = str(reading.reading_id)
    existing = session.get(SensorReadingRow, reading_id)
    new_hash = _payload_hash(reading)

    if existing is not None:
        if existing.payload_hash != new_hash:
            raise ApiError("IDEMPOTENCY_CONFLICT", f"reading_id {reading_id} already exists with different payload", status_code=409)
        return _row_to_out(existing), False

    row = SensorReadingRow(
        reading_id=reading_id,
        sensor_id=reading.sensor_id,
        zone_id=reading.zone_id,
        scenario_id=reading.scenario_id,
        gas=reading.gas.value,
        value=reading.value,
        unit=reading.unit.value,
        event_time=reading.event_time,
        ingested_at=now,
        source=reading.source.value,
        quality=reading.quality.value,
        sequence_number=reading.sequence_number,
        correlation_id=str(reading.correlation_id) if reading.correlation_id else None,
        fault_code=reading.fault_code,
        payload_hash=new_hash,
    )
    session.add(row)
    session.commit()
    return _row_to_out(row), True


def _row_to_out(row: SensorReadingRow) -> SensorReadingOut:
    return SensorReadingOut(
        reading_id=row.reading_id,
        sensor_id=row.sensor_id,
        zone_id=row.zone_id,
        scenario_id=row.scenario_id,
        gas=row.gas,
        value=row.value,
        unit=row.unit,
        event_time=row.event_time,
        ingested_at=row.ingested_at,
        source=row.source,
        quality=row.quality,
        sequence_number=row.sequence_number,
        correlation_id=row.correlation_id,
        fault_code=row.fault_code,
    )
