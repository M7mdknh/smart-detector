"""Phase 5: benchmarks last-value persistence, physics-only, and physics+GRU
residual forecasting on the held-out GRU TEST split (never used for training or
threshold selection). Reports globally and by scenario category, and separates
two forecasting conditions:

  - "observable": the input window already shows a developing trend/residual
    in the last 30 minutes before the cutoff (|residual| exceeds a fixed
    threshold in at least one of the last 6 input steps).
  - "unannounced": no such precursor is visible in the input window -- a new
    onset starting after the cutoff. The GRU (or any model conditioned only on
    history) cannot be expected to anticipate this; reported as a structural
    information limit, not scored as a model failure.

`make evaluate-forecast` runs this script. Promotion decision is written to
models/evaluation/gru_promotion_decision.json based on the measured numbers,
not asserted in advance.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.inference.forecast_gru import get_forecast_gru  # noqa: E402
from app.inference.gru_dataset import OUTPUT_STEPS, build_windows_for_scenario  # noqa: E402
from app.inference.synthetic_scenarios import generate_scenario_dataframe, gru_scenario_specs  # noqa: E402
from scripts.train_forecast_gru import split_scenarios  # noqa: E402

MODELS_DIR = REPO_ROOT / "models"
EVAL_DIR = MODELS_DIR / "evaluation"
ARTIFACTS_DIR = MODELS_DIR / "artifacts"

PRECURSOR_RESIDUAL_PPM = 150.0  # |residual| in any of the last 6 input steps counts as an observable precursor
STEP_MINUTES = 5


def is_observable(window) -> bool:
    residual_norm = window.X[-6:, 2]  # last 30 minutes, feature index 2 = residual_norm (raw/5000)
    return bool(np.any(np.abs(residual_norm) * 5000.0 >= PRECURSOR_RESIDUAL_PPM))


def crossing_time_error(y_actual, y_forecast, threshold=5000.0) -> float | None:
    """Minutes-to-cross error: None if neither actual nor forecast crosses within
    the horizon (not comparable)."""
    def first_cross(series):
        for k, v in enumerate(series):
            if v >= threshold:
                return (k + 1) * STEP_MINUTES
        return None

    actual_t = first_cross(y_actual)
    forecast_t = first_cross(y_forecast)
    if actual_t is None and forecast_t is None:
        return None
    if actual_t is None or forecast_t is None:
        return 60.0  # one crossed, the other didn't within horizon: max horizon error
    return abs(actual_t - forecast_t)


def main():
    print("Regenerating the GRU TEST split (same seed/split logic as training)...")
    specs = gru_scenario_specs(n_per_kind=20)
    _, _, test_specs = split_scenarios(specs)

    windows_by_kind: dict[str, list] = {}
    for spec in test_specs:
        df = generate_scenario_dataframe(spec)
        ws = build_windows_for_scenario(df, spec.scenario_id)
        windows_by_kind.setdefault(spec.kind, []).extend(ws)

    all_windows = [w for ws in windows_by_kind.values() for w in ws]
    print(f"test windows: {len(all_windows)} across {len(windows_by_kind)} categories")

    gru = get_forecast_gru()
    print(f"GRU adapter status: {gru.status.value}")

    rows = []
    latencies = []
    for kind, windows in windows_by_kind.items():
        for w in windows:
            t0 = time.perf_counter()
            gru_result = gru.predict(w.X)
            latencies.append(time.perf_counter() - t0)

            persistence_forecast = np.full(OUTPUT_STEPS, w.X[-1, 0] * 10000.0)  # last observed, denormalized
            physics_forecast = w.y_physics_forecast
            if gru_result.status.value == "OK" and gru_result.residuals is not None:
                hybrid_forecast = physics_forecast + np.array(gru_result.residuals)
            else:
                hybrid_forecast = physics_forecast  # fallback: physics-only

            rows.append({
                "kind": kind,
                "observable": is_observable(w),
                "actual": w.y_actual,
                "persistence": persistence_forecast,
                "physics": physics_forecast,
                "hybrid": hybrid_forecast,
            })

    def metrics_for(rows_subset, model_key):
        if not rows_subset:
            return None
        errors = np.array([r[model_key] - r["actual"] for r in rows_subset])
        mae = float(np.mean(np.abs(errors)))
        rmse = float(np.sqrt(np.mean(errors**2)))
        worst = float(np.max(np.abs(errors)))
        p95 = float(np.percentile(np.abs(errors), 95))

        crossing_errors = [crossing_time_error(r["actual"], r[model_key]) for r in rows_subset]
        crossing_errors = [c for c in crossing_errors if c is not None]
        crossing_mae = float(np.mean(crossing_errors)) if crossing_errors else None

        return {"mae": mae, "rmse": rmse, "worst_case_abs_error": worst, "p95_abs_error": p95, "crossing_time_mae_minutes": crossing_mae, "n": len(rows_subset)}

    report = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "gru_status": gru.status.value}

    report["global"] = {
        "persistence": metrics_for(rows, "persistence"),
        "physics": metrics_for(rows, "physics"),
        "hybrid_physics_plus_gru": metrics_for(rows, "hybrid"),
    }

    report["by_category"] = {}
    for kind in windows_by_kind:
        subset = [r for r in rows if r["kind"] == kind]
        report["by_category"][kind] = {
            "persistence": metrics_for(subset, "persistence"),
            "physics": metrics_for(subset, "physics"),
            "hybrid_physics_plus_gru": metrics_for(subset, "hybrid"),
        }

    observable_rows = [r for r in rows if r["observable"]]
    unannounced_rows = [r for r in rows if not r["observable"]]
    report["observable_precursor_condition"] = {
        "n": len(observable_rows),
        "physics": metrics_for(observable_rows, "physics"),
        "hybrid_physics_plus_gru": metrics_for(observable_rows, "hybrid"),
    }
    report["unannounced_onset_condition"] = {
        "n": len(unannounced_rows),
        "physics": metrics_for(unannounced_rows, "physics"),
        "hybrid_physics_plus_gru": metrics_for(unannounced_rows, "hybrid"),
        "note": "No observable precursor in the input window by construction. Neither physics nor the "
                "GRU can be expected to anticipate this -- reported as a structural information limit.",
    }

    report["inference_latency_ms"] = {
        "median": float(np.median(latencies) * 1000) if latencies else None,
        "p95": float(np.percentile(latencies, 95) * 1000) if latencies else None,
    }

    # --- promotion decision ---
    phys_mae = report["global"]["physics"]["mae"] if report["global"]["physics"] else None
    hybrid_mae = report["global"]["hybrid_physics_plus_gru"]["mae"] if report["global"]["hybrid_physics_plus_gru"] else None
    phys_worst = report["global"]["physics"]["worst_case_abs_error"] if report["global"]["physics"] else None
    hybrid_worst = report["global"]["hybrid_physics_plus_gru"]["worst_case_abs_error"] if report["global"]["hybrid_physics_plus_gru"] else None
    phys_crossing = report["global"]["physics"]["crossing_time_mae_minutes"]
    hybrid_crossing = report["global"]["hybrid_physics_plus_gru"]["crossing_time_mae_minutes"]

    improves_mae = hybrid_mae is not None and phys_mae is not None and hybrid_mae < phys_mae * 0.95  # >=5% real improvement
    no_worst_case_regression = hybrid_worst is not None and phys_worst is not None and hybrid_worst <= phys_worst * 1.10  # <=10% worse allowed
    crossing_ok = (hybrid_crossing is None) or (phys_crossing is None) or (hybrid_crossing <= phys_crossing * 1.10)
    fast_enough = report["inference_latency_ms"]["p95"] is not None and report["inference_latency_ms"]["p95"] < 5000.0  # well under the 5-min cadence

    promote = improves_mae and no_worst_case_regression and crossing_ok and fast_enough

    decision = {
        "promote_hybrid_as_default": promote,
        "criteria": {
            "improves_mae_by_5pct_or_more": improves_mae,
            "no_worst_case_regression_over_10pct": no_worst_case_regression,
            "crossing_time_not_worse_by_10pct": crossing_ok,
            "fast_enough_for_5min_cadence": fast_enough,
        },
        "measured": {"physics_mae": phys_mae, "hybrid_mae": hybrid_mae, "physics_worst": phys_worst, "hybrid_worst": hybrid_worst},
        "explanation": (
            "Hybrid promoted as the default combined forecast." if promote else
            "Hybrid does NOT meet the promotion bar on this held-out test set -- kept as an EXPERIMENTAL "
            "model. Physics remains the default forecast. This is reported as a measured negative result, "
            "not forced to a favorable conclusion. Additional real (non-synthetic) training data, more "
            "training epochs, or richer features would be the concrete next steps to revisit this."
        ),
    }
    report["promotion_decision"] = decision

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVAL_DIR / "gru_benchmark_report.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
