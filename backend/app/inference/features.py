"""Leakage-safe feature vector for the leak classifier.

Shared by training and runtime inference so features are computed identically.
Only uses data at or before the cutoff time. See CLAUDE.md / model-specification.md
for the exact feature list and the leakage exclusions (no scenario ID, seed,
future control state, future readings, incident severity, or simulator leak flag).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

FEATURE_NAMES = [
    "current_ppm",
    "delta_5m",
    "delta_15m",
    "delta_30m",
    "slope_15m",
    "slope_30m",
    "slope_60m",
    "rollmean_15m",
    "rollstd_15m",
    "rollmean_30m",
    "rollstd_30m",
    "rollmean_60m",
    "rollstd_60m",
    "deviation_from_no_leak_physics",
    "ventilation_m3h",
    "ventilation_delta_30m",
    "missing_fraction_60m",
]


@dataclass(frozen=True)
class FeatureFrame:
    columns: list[str]
    values: np.ndarray  # shape (n_samples, n_features)


def _robust_slope(t_minutes: np.ndarray, y: np.ndarray) -> float:
    """Theil-Sen-like robust slope (median of pairwise slopes) in ppm/minute."""
    n = len(y)
    if n < 2:
        return 0.0
    slopes = []
    for i in range(n):
        for j in range(i + 1, n):
            dt = t_minutes[j] - t_minutes[i]
            if dt > 0:
                slopes.append((y[j] - y[i]) / dt)
    if not slopes:
        return 0.0
    return float(np.median(slopes))


def compute_features_at_cutoff(
    history: pd.DataFrame,
    cutoff_minute: float,
    ventilation_m3h: float,
    ventilation_30m_ago_m3h: float,
    no_leak_expected_ppm: float,
) -> np.ndarray:
    """history: DataFrame with columns ['minute', 'ppm', 'missing'] at 5-min cadence,
    minute values <= cutoff_minute only (enforced by caller/window slicing).
    """
    h = history[history["minute"] <= cutoff_minute].sort_values("minute")
    if h.empty:
        return np.zeros(len(FEATURE_NAMES))

    current = float(h["ppm"].iloc[-1])

    def value_at(back_minutes: float) -> float:
        target = cutoff_minute - back_minutes
        window = h[h["minute"] <= target]
        if window.empty:
            return current
        return float(window["ppm"].iloc[-1])

    delta_5 = current - value_at(5)
    delta_15 = current - value_at(15)
    delta_30 = current - value_at(30)

    def slope_over(minutes: float) -> float:
        window = h[h["minute"] >= cutoff_minute - minutes]
        if len(window) < 2:
            return 0.0
        return _robust_slope(window["minute"].to_numpy(), window["ppm"].to_numpy())

    def rollstat(minutes: float) -> tuple[float, float]:
        window = h[h["minute"] >= cutoff_minute - minutes]
        if window.empty:
            return current, 0.0
        return float(window["ppm"].mean()), float(window["ppm"].std(ddof=0) or 0.0)

    mean15, std15 = rollstat(15)
    mean30, std30 = rollstat(30)
    mean60, std60 = rollstat(60)

    window60 = h[h["minute"] >= cutoff_minute - 60]
    missing_fraction = float(window60["missing"].mean()) if not window60.empty else 0.0

    deviation = current - no_leak_expected_ppm
    vent_delta = ventilation_m3h - ventilation_30m_ago_m3h

    values = [
        current,
        delta_5,
        delta_15,
        delta_30,
        slope_over(15),
        slope_over(30),
        slope_over(60),
        mean15,
        std15,
        mean30,
        std30,
        mean60,
        std60,
        deviation,
        ventilation_m3h,
        vent_delta,
        missing_fraction,
    ]
    return np.array(values, dtype=float)
