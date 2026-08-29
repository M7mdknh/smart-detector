"""Leakage-safe windowed dataset for the physics-informed residual GRU.

Data contract (sensor-risk-modeling model-specification.md): 10h history / 120
five-minute input steps, one-hour / 12-step forecast horizon. Reuses the same
synthetic-scenario generator as the XGBoost leak classifier
(app.inference.synthetic_scenarios) and the live simulator's own physics code
(app.domain.physics.mass_balance) -- so training-time physics baselines cannot
drift from what the runtime forecast service computes.

Two physics quantities are computed, deliberately different:

- `physics_one_step`: at each PAST input timestep, physics's own next-tick
  estimate from the previous OBSERVED value and that tick's actual known
  ventilation/source. This is a feature (input), not a target -- it lets the
  GRU see how much physics itself was already "surprised" moment to moment.
- `physics_forecast_from_cutoff`: at the prediction cutoff, physics projected
  forward 60 minutes using ONLY the segment parameters known AT the cutoff,
  held constant -- exactly what app/services/forecast_service.py computes at
  serve time. The GRU's target is the residual between this cutoff-anchored
  forecast and what actually happened, i.e. exactly the correction available
  at inference time (no peeking at future control changes).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.domain.physics.mass_balance import Segment, concentration_at

INPUT_STEPS = 120
OUTPUT_STEPS = 12
STEP_MINUTES = 5
VOLUME_M3 = 1000.0
INLET_PPM = 450.0

# Feature order is part of the versioned contract (see feature_schema.json).
FEATURE_NAMES = [
    "observed_co2_norm",
    "physics_one_step_norm",
    "residual_norm",
    "ventilation_norm",
    "source_norm",
    "missing_mask",
    "quality_flag",
]


@dataclass(frozen=True)
class GruWindow:
    scenario_id: str
    cutoff_minute: float
    X: np.ndarray  # (INPUT_STEPS, len(FEATURE_NAMES)) -- normalized
    y_residual: np.ndarray  # (OUTPUT_STEPS,) -- raw ppm residual (physics_forecast vs actual)
    y_physics_forecast: np.ndarray  # (OUTPUT_STEPS,) -- raw ppm, for reconstructing combined = physics + residual
    y_actual: np.ndarray  # (OUTPUT_STEPS,) -- raw ppm ground truth, for evaluation only


def compute_physics_one_step_series(df: pd.DataFrame) -> np.ndarray:
    """physics_one_step[i]: physics's next-tick estimate at row i, computed from
    row i-1's OBSERVED value and row i's known controls (causal: never uses
    row i's own observed value)."""
    values = df["ppm"].to_numpy()
    ventilation = df["ventilation_m3h"].to_numpy()
    source = df["source_ppm_m3h"].to_numpy()

    out = np.empty(len(df))
    c_prev = INLET_PPM
    for i in range(len(df)):
        seg = Segment(VOLUME_M3, INLET_PPM, float(ventilation[i]), float(source[i]), STEP_MINUTES / 60.0)
        out[i] = concentration_at(seg, c_prev, STEP_MINUTES / 60.0)
        c_prev = values[i]  # next step's "previous observed" is this tick's real reading
    return out


def physics_forecast_from_cutoff(ventilation_at_cutoff: float, source_at_cutoff: float, c0: float) -> np.ndarray:
    """12-point, 5-min-step physics forecast using ONLY cutoff-time-known
    parameters held constant -- identical contract to forecast_service.build_forecast."""
    seg = Segment(VOLUME_M3, INLET_PPM, ventilation_at_cutoff, source_at_cutoff, STEP_MINUTES / 60.0)
    out = np.empty(OUTPUT_STEPS)
    c = c0
    for k in range(OUTPUT_STEPS):
        c = concentration_at(seg, c, STEP_MINUTES / 60.0)
        out[k] = c
    return out


def build_windows_for_scenario(df: pd.DataFrame, scenario_id: str, stride_minutes: float = 15.0) -> list[GruWindow]:
    """df must have columns: minute, ppm, ventilation_m3h, source_ppm_m3h, missing
    (as produced by app.inference.synthetic_scenarios.generate_scenario_dataframe),
    at the canonical 5-minute cadence."""
    physics_one_step = compute_physics_one_step_series(df)
    residual = df["ppm"].to_numpy() - physics_one_step
    ventilation = df["ventilation_m3h"].to_numpy()
    source = df["source_ppm_m3h"].to_numpy()
    missing = df["missing"].to_numpy() if "missing" in df.columns else np.zeros(len(df))
    minutes = df["minute"].to_numpy()
    observed = df["ppm"].to_numpy()

    max_minute = minutes.max()
    windows: list[GruWindow] = []

    cutoff = INPUT_STEPS * STEP_MINUTES  # first cutoff needs a full 120-step history
    while cutoff + OUTPUT_STEPS * STEP_MINUTES <= max_minute:
        cutoff_idx = int(round(cutoff / STEP_MINUTES))
        input_start_idx = cutoff_idx - INPUT_STEPS
        if input_start_idx < 0:
            cutoff += stride_minutes
            continue

        X = np.zeros((INPUT_STEPS, len(FEATURE_NAMES)), dtype=np.float64)
        # Normalization here is a fixed, documented linear scale (not fit per-window):
        # true training-set normalization statistics are computed once over the TRAIN
        # split only in scripts/train_forecast_gru.py and stored in the scaler artifact;
        # this function emits raw + a light fixed pre-scale so windows are comparable
        # before that global fit is applied.
        X[:, 0] = observed[input_start_idx:cutoff_idx] / 10000.0
        X[:, 1] = physics_one_step[input_start_idx:cutoff_idx] / 10000.0
        X[:, 2] = residual[input_start_idx:cutoff_idx] / 5000.0
        X[:, 3] = ventilation[input_start_idx:cutoff_idx] / 1000.0
        X[:, 4] = source[input_start_idx:cutoff_idx] / 8_000_000.0
        X[:, 5] = missing[input_start_idx:cutoff_idx]
        X[:, 6] = 1.0 - missing[input_start_idx:cutoff_idx]  # quality_flag: 1=good, 0=imputed/missing

        c0 = observed[cutoff_idx - 1]
        forecast = physics_forecast_from_cutoff(float(ventilation[cutoff_idx - 1]), float(source[cutoff_idx - 1]), c0)

        future_idx = [cutoff_idx + k for k in range(1, OUTPUT_STEPS + 1)]
        if future_idx[-1] >= len(df):
            cutoff += stride_minutes
            continue
        y_actual = observed[future_idx]
        y_residual = y_actual - forecast

        windows.append(
            GruWindow(
                scenario_id=scenario_id, cutoff_minute=cutoff, X=X,
                y_residual=y_residual, y_physics_forecast=forecast, y_actual=y_actual,
            )
        )
        cutoff += stride_minutes

    return windows
