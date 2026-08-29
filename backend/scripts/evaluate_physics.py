"""Reproduces physics forecast MAE/RMSE and crossing-time error (make evaluate)."""

import json
import sys
import time
from pathlib import Path

import numpy as np

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.physics.forecast import evaluate_crossing, forecast_points  # noqa: E402
from app.domain.physics.mass_balance import Segment  # noqa: E402
from app.inference.synthetic_scenarios import ScenarioSpec, generate_scenario_dataframe  # noqa: E402

EVAL_DIR = REPO_ROOT / "models" / "evaluation"


def main():
    from datetime import datetime, timezone

    errors = []
    crossing_errors = []

    specs = [ScenarioSpec(scenario_id=f"eval-leak-{i}", seed=5000 + i, kind="leak") for i in range(10)]

    for spec in specs:
        df = generate_scenario_dataframe(spec)
        # Pick a cutoff partway through and compare 60-min-ahead physics forecast to
        # the actual generated values at those future minutes (same generator/seed).
        max_minute = df["minute"].max()
        cutoff = max_minute * 0.4
        row_at_cutoff = df[df["minute"] <= cutoff].iloc[-1]
        source = float(row_at_cutoff["source_ppm_m3h"])
        ventilation = float(row_at_cutoff["ventilation_m3h"])
        c0 = float(row_at_cutoff["ppm"])

        seg = Segment(volume_m3=1000.0, inlet_ppm=450.0, ventilation_m3h=ventilation, source_ppm_m3h=source, duration_hours=1.0)
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        points = forecast_points(seg, c0, now)

        for i, p in enumerate(points):
            target_minute = cutoff + p.horizon_minutes
            actual_row = df[df["minute"] >= target_minute]
            if actual_row.empty:
                continue
            actual = float(actual_row.iloc[0]["ppm"])
            errors.append(p.physics_ppm - actual)

        crossing = evaluate_crossing(seg, c0, "action", 5000.0)
        if crossing.minutes_to_cross is not None:
            predicted_cross_minute = cutoff + crossing.minutes_to_cross
            actual_cross = df[df["ppm"] >= 5000.0]
            if not actual_cross.empty:
                actual_cross_minute = float(actual_cross.iloc[0]["minute"])
                crossing_errors.append(predicted_cross_minute - actual_cross_minute)

    errors = np.array(errors)
    mae = float(np.mean(np.abs(errors))) if len(errors) else None
    rmse = float(np.sqrt(np.mean(errors**2))) if len(errors) else None

    crossing_errors = np.array(crossing_errors)
    crossing_mae = float(np.mean(np.abs(crossing_errors))) if len(crossing_errors) else None

    report = {
        "n_scenarios": len(specs),
        "n_point_comparisons": int(len(errors)),
        "physics_mae_ppm": mae,
        "physics_rmse_ppm": rmse,
        "n_crossing_comparisons": int(len(crossing_errors)),
        "crossing_time_mae_minutes": crossing_mae,
        "note": "Physics forecast is deterministic given (V, Cin, Q, G); this reports "
                "forecast error against the sensor-noise-perturbed generated trajectory "
                "under piecewise-constant controls, not against real-world data (no real "
                "deployment data exists for this synthetic prototype).",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVAL_DIR / "physics_forecast_metrics.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
