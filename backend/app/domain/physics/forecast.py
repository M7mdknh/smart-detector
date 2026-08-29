"""60-minute / 12-point physics forecast and typed threshold crossings."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.contracts.enums import CrossingOutcome
from app.domain.physics.mass_balance import (
    InvalidPhysicsParameters,
    Segment,
    concentration_at,
    time_to_threshold_hours,
)

STEP_MINUTES = 5
HORIZON_MINUTES = 60
N_POINTS = HORIZON_MINUTES // STEP_MINUTES


@dataclass(frozen=True)
class ForecastPointResult:
    horizon_minutes: int
    event_time: datetime
    physics_ppm: float


@dataclass(frozen=True)
class CrossingResult:
    threshold_name: str
    threshold_ppm: float
    outcome: CrossingOutcome
    minutes_to_cross: float | None


def forecast_points(
    seg: Segment, c0_ppm: float, based_on: datetime
) -> list[ForecastPointResult]:
    step_hours = STEP_MINUTES / 60.0
    points: list[ForecastPointResult] = []
    c = c0_ppm
    for i in range(1, N_POINTS + 1):
        c = concentration_at(seg, c, step_hours)
        points.append(
            ForecastPointResult(
                horizon_minutes=i * STEP_MINUTES,
                event_time=based_on + timedelta(minutes=i * STEP_MINUTES),
                physics_ppm=c,
            )
        )
    return points


def evaluate_crossing(
    seg: Segment, c0_ppm: float, threshold_name: str, threshold_ppm: float
) -> CrossingResult:
    """Typed crossing outcome for one threshold within the 60-minute horizon."""
    try:
        if c0_ppm >= threshold_ppm:
            return CrossingResult(threshold_name, threshold_ppm, CrossingOutcome.ALREADY_EXCEEDED, 0.0)

        t_hours = time_to_threshold_hours(seg, c0_ppm, threshold_ppm)
    except InvalidPhysicsParameters:
        return CrossingResult(threshold_name, threshold_ppm, CrossingOutcome.INVALID_PARAMETERS, None)

    if t_hours is None:
        return CrossingResult(threshold_name, threshold_ppm, CrossingOutcome.NO_CROSSING, None)

    minutes = t_hours * 60.0
    if minutes > HORIZON_MINUTES:
        return CrossingResult(threshold_name, threshold_ppm, CrossingOutcome.NO_CROSSING, None)

    return CrossingResult(threshold_name, threshold_ppm, CrossingOutcome.CROSSING_EXPECTED, minutes)
