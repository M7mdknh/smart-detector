from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.contracts.enums import CrossingOutcome, Gas, ModelStatus


class ForecastPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    horizon_minutes: int
    event_time: datetime
    physics_ppm: float
    residual_ppm: float | None = None
    predicted_ppm: float
    lower_ppm: float | None = None
    upper_ppm: float | None = None


class Crossing(BaseModel):
    threshold_name: str
    threshold_ppm: float
    outcome: CrossingOutcome
    minutes_to_cross: float | None = None


class Forecast(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    forecast_id: UUID
    zone_id: str
    gas: Gas
    generated_at: datetime
    based_on_event_time: datetime

    physics_model_version: str
    ml_model_version: str | None = None
    model_status: ModelStatus
    gru_model_version: str | None = None
    gru_status: ModelStatus = ModelStatus.UNAVAILABLE

    horizon_minutes: int = 60
    step_minutes: int = 5
    points: list[ForecastPoint]

    leak_probability: float | None = None
    leak_label: str | None = None
    calibration_version: str | None = None
    feature_snapshot_ref: str | None = None

    crossings: list[Crossing]
