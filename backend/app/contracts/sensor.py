from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.contracts.enums import Gas, ReadingQuality, ReadingSource, Unit


class SensorReadingIn(BaseModel):
    """Public ingestion contract. Used identically by the simulator, replay, and future devices."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    reading_id: UUID
    sensor_id: str = Field(min_length=1, max_length=64)
    zone_id: str = Field(min_length=1, max_length=64)
    scenario_id: str = Field(min_length=1, max_length=64)

    gas: Gas
    value: float
    unit: Unit

    event_time: datetime
    source: ReadingSource
    quality: ReadingQuality = ReadingQuality.GOOD

    sequence_number: int | None = None
    correlation_id: UUID | None = None
    fault_code: str | None = None

    @field_validator("value")
    @classmethod
    def finite_value(cls, v: float) -> float:
        import math

        if not math.isfinite(v):
            raise ValueError("value must be a finite number")
        if v < 0:
            raise ValueError("value must be non-negative")
        return v

    @field_validator("event_time")
    @classmethod
    def tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("event_time must be timezone-aware")
        return v


class SensorReadingOut(SensorReadingIn):
    ingested_at: datetime


class SensorHistoryResponse(BaseModel):
    zone_id: str
    gas: Gas
    readings: list[SensorReadingOut]
