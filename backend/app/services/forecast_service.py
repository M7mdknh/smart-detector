"""Builds the 60-minute physics forecast, exposure figures, and leak probability."""

import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.enums import ModelStatus
from app.domain.exposure.rolling import TimedValue, rolling_short_term, rolling_twa
from app.domain.physics.forecast import evaluate_crossing, forecast_points
from app.domain.physics.mass_balance import Segment, concentration_at
from app.inference.features import FEATURE_NAMES, compute_features_at_cutoff
from app.inference.forecast_gru import get_forecast_gru
from app.inference.gru_dataset import INPUT_STEPS, OUTPUT_STEPS
from app.inference.leak_model import get_leak_model
from app.settings import get_settings
from app.storage.models import ForecastRow, SensorReadingRow, SimulationRunRow

PHYSICS_MODEL_VERSION = "1.0"


def _build_gru_feature_window(readings: list[SensorReadingRow], run: SimulationRunRow) -> np.ndarray | None:
    """Builds the (INPUT_STEPS, 7) feature window from the most recent readings,
    matching app/inference/gru_dataset.py's feature order and fixed pre-scale.

    Simplification, documented honestly (docs/README.md): historical per-tick
    ventilation/source values aren't persisted per reading, only the current
    run's live values -- unlike training data (which has true historical
    per-tick controls), live inference uses the CURRENT ventilation/source
    held constant across the lookback window. This is a real train/serve
    skew when controls changed recently within the lookback; physics remains
    the authoritative forecast regardless, so this only affects the size of
    the optional GRU correction, never correctness of the safety-relevant path.

    Second, narrower documented skew (found and pinned down by
    backend/tests/test_gru_train_serve_parity.py): the "physics_one_step"
    causal chain used to build columns 1 (physics_one_step_norm) and 2
    (residual_norm) is seeded here from `run.inlet_co2_ppm` for row 0 of the
    120-step window, because `_lookback_readings` only fetches the window
    itself and has no access to the actual reading immediately preceding it.
    Offline training (app/inference/gru_dataset.py) computes the same chain
    once over the WHOLE scenario and slices it, so its row 0 is seeded from
    the true preceding observed reading instead. This makes row 0 (of 120)
    on those 2 (of 7) feature columns differ from what the model saw in
    training whenever that preceding reading is not close to the inlet
    baseline (450 ppm) -- rows 1-119 are unaffected, and physics/thresholds
    are entirely unaffected; only the size of the optional GRU residual can
    shift slightly. Not fixed here because it would require persisting one
    extra reading of lookback and is out of scope for this audit pass; see
    docs/README.md's GRU section for the corresponding promotion-language
    caveat.
    """
    if len(readings) < INPUT_STEPS:
        return None
    window = readings[-INPUT_STEPS:]
    values = np.array([r.value for r in window], dtype=np.float64)
    missing = np.array([1.0 if r.quality in ("MISSING", "IMPUTED") else 0.0 for r in window], dtype=np.float64)

    ventilation = run.ventilation_m3_per_h
    source = run.source_ppm_m3_per_h
    seg = Segment(volume_m3=run.zone_volume_m3, inlet_ppm=run.inlet_co2_ppm, ventilation_m3h=ventilation, source_ppm_m3h=source, duration_hours=5.0 / 60.0)

    physics_one_step = np.empty(INPUT_STEPS)
    c_prev = run.inlet_co2_ppm
    for i in range(INPUT_STEPS):
        physics_one_step[i] = concentration_at(seg, c_prev, 5.0 / 60.0)
        c_prev = values[i]
    residual = values - physics_one_step

    X = np.zeros((INPUT_STEPS, 7), dtype=np.float64)
    X[:, 0] = values / 10000.0
    X[:, 1] = physics_one_step / 10000.0
    X[:, 2] = residual / 5000.0
    X[:, 3] = ventilation / 1000.0
    X[:, 4] = source / 8_000_000.0
    X[:, 5] = missing
    X[:, 6] = 1.0 - missing
    return X


def _lookback_readings(session: Session, zone_id: str, gas: str, now: datetime, hours: float) -> list[SensorReadingRow]:
    since = now - timedelta(hours=hours)
    stmt = (
        select(SensorReadingRow)
        .where(SensorReadingRow.zone_id == zone_id, SensorReadingRow.gas == gas, SensorReadingRow.event_time >= since, SensorReadingRow.event_time <= now)
        .order_by(SensorReadingRow.event_time)
    )
    return list(session.execute(stmt).scalars())


def build_forecast(session: Session, run: SimulationRunRow, now: datetime) -> ForecastRow | None:
    settings = get_settings()
    readings = _lookback_readings(session, run.zone_id if hasattr(run, "zone_id") else "zone-1", "CO2", now, settings.lookback_hours)
    if not readings:
        return None

    current_ppm = readings[-1].value
    seg = Segment(
        volume_m3=run.zone_volume_m3,
        inlet_ppm=run.inlet_co2_ppm,
        ventilation_m3h=run.ventilation_m3_per_h,
        source_ppm_m3h=run.source_ppm_m3_per_h,
        duration_hours=settings.forecast_horizon_minutes / 60.0,
    )

    points = forecast_points(seg, current_ppm, now)

    action_crossing = evaluate_crossing(seg, current_ppm, "NIOSH_ACTION_5000", settings.niosh_twa_ppm)
    idlh_crossing = evaluate_crossing(seg, current_ppm, "NIOSH_IDLH_40000", settings.niosh_idlh_ppm)
    advisory_crossing = evaluate_crossing(seg, current_ppm, "INTERNAL_ADVISORY_1000", settings.internal_ventilation_advisory_ppm)

    # No-leak physics baseline: same segment but source held at 0 (used as ML feature and severity context)
    no_leak_seg = Segment(volume_m3=run.zone_volume_m3, inlet_ppm=run.inlet_co2_ppm, ventilation_m3h=run.ventilation_m3_per_h, source_ppm_m3h=0.0, duration_hours=0.0)
    from app.domain.physics.mass_balance import concentration_at

    no_leak_expected = concentration_at(no_leak_seg, current_ppm, 5.0 / 60.0)

    # Build feature history frame from lookback readings at 5-min cadence
    base_time = readings[0].event_time
    rows = []
    for r in readings:
        minute = (r.event_time - base_time).total_seconds() / 60.0
        rows.append({"minute": minute, "ppm": r.value, "missing": 1 if r.quality in ("MISSING", "IMPUTED") else 0})
    history_df = pd.DataFrame(rows)
    cutoff_minute = (now - base_time).total_seconds() / 60.0

    features = compute_features_at_cutoff(
        history_df,
        cutoff_minute,
        run.ventilation_m3_per_h,
        run.ventilation_m3_per_h,  # 30-min-ago ventilation not tracked separately in P0; treat as unchanged
        no_leak_expected,
    )

    slope_30 = float(features[FEATURE_NAMES.index("slope_30m")])
    is_leak_consistent = run.source_ppm_m3_per_h > 0
    persistence = min(len(readings), 6)

    leak_result = get_leak_model().predict(features, slope_30, is_leak_consistent, persistence)

    model_status = ModelStatus.OK if leak_result.status == ModelStatus.OK else ModelStatus.FALLBACK

    # Physics-informed residual GRU: purely additive. Physics (`points`) is already
    # fully computed above and is what forms the forecast/crossings regardless of
    # whether this succeeds -- ingestion, thresholds, and Time-to-Action never wait
    # on or depend on this call.
    gru_status = ModelStatus.UNAVAILABLE
    gru_version = None
    residuals = lowers = uppers = [None] * OUTPUT_STEPS
    feature_window = _build_gru_feature_window(readings, run)
    if feature_window is not None:
        gru_result = get_forecast_gru().predict(feature_window)
        gru_status = gru_result.status
        gru_version = gru_result.model_version
        if gru_result.status == ModelStatus.OK and gru_result.residuals is not None:
            residuals = gru_result.residuals
            lowers = gru_result.lower_bounds
            uppers = gru_result.upper_bounds

    points_json = [
        {
            "horizon_minutes": p.horizon_minutes,
            "event_time": p.event_time.isoformat(),
            "physics_ppm": p.physics_ppm,
            "residual_ppm": residuals[i],
            "predicted_ppm": max(0.0, p.physics_ppm + residuals[i]) if residuals[i] is not None else p.physics_ppm,
            "lower_ppm": (max(0.0, p.physics_ppm + lowers[i]) if lowers[i] is not None else None),
            "upper_ppm": (max(0.0, p.physics_ppm + uppers[i]) if uppers[i] is not None else None),
        }
        for i, p in enumerate(points)
    ]
    crossings_json = [
        {"threshold_name": c.threshold_name, "threshold_ppm": c.threshold_ppm, "outcome": c.outcome.value, "minutes_to_cross": c.minutes_to_cross}
        for c in (action_crossing, idlh_crossing, advisory_crossing)
    ]

    row = ForecastRow(
        forecast_id=str(uuid.uuid4()),
        zone_id=readings[-1].zone_id,
        gas="CO2",
        generated_at=now,
        based_on_event_time=readings[-1].event_time,
        physics_model_version=PHYSICS_MODEL_VERSION,
        ml_model_version=leak_result.model_version,
        model_status=model_status.value,
        gru_model_version=gru_version,
        gru_status=gru_status.value,
        horizon_minutes=settings.forecast_horizon_minutes,
        step_minutes=settings.forecast_step_minutes,
        points_json=points_json,
        leak_probability=leak_result.probability,
        leak_label=leak_result.label.value,
        calibration_version=leak_result.calibration_version,
        feature_snapshot_json=leak_result.feature_snapshot,
        crossings_json=crossings_json,
    )
    session.add(row)
    session.commit()
    return row


def exposure_snapshot(session: Session, zone_id: str, now: datetime) -> dict:
    readings = _lookback_readings(session, zone_id, "CO2", now, 8.0)
    timed = [TimedValue(r.event_time, r.value) for r in readings]
    short_term = rolling_short_term(timed, now)
    twa, partial = rolling_twa(timed, now)
    return {"short_term_avg_ppm": short_term, "twa_ppm": twa, "twa_partial_window": partial}
