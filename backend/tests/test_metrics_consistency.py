"""Guards against the physics-vs-GRU metrics reconciliation drifting silently.

Two different, non-comparable evaluation harnesses both produce a "physics MAE"
number, and it is easy to accidentally quote one where the other belongs
(this happened in an earlier submission draft: several docs rounded/quoted
the matched-comparison improvement as a flat "17%" while the precise value is
16.8%, and one row wrongly reused that same rounded figure for a different
scenario subset). This test recomputes the improvement percentages directly
from the generated JSON artifacts and asserts they match what the docs are
allowed to claim, so any future retraining/re-evaluation run that changes the
underlying numbers without updating the docs is caught here rather than
silently shipping a stale, wrong percentage.

- `models/evaluation/physics_forecast_metrics.json`: the general/broad
  physics-only evaluation (10 held-out scenarios, 120 point-comparisons).
  Kept intentionally separate -- it is not compared against the GRU hybrid
  number below; that would be an apples-to-oranges comparison across two
  different scenario populations.
- `models/evaluation/gru_benchmark_report.json`: the GRU benchmark's own
  matched physics-vs-hybrid comparison, same held-out TEST-split windows for
  both columns (1,092 point-comparisons globally).
"""

import json
import math

import pytest

from app.settings import get_settings

EVAL_DIR = get_settings().models_dir / "evaluation"


def _round1(x: float) -> float:
    return round(x, 1)


def test_physics_only_metric_is_a_distinct_population_from_the_gru_benchmark():
    """The two "physics MAE" numbers must never be silently equal or conflated
    -- they come from different scenario populations (10 broad scenarios vs.
    1,092 GRU held-out-test-split windows) and are documented separately."""
    physics_path = EVAL_DIR / "physics_forecast_metrics.json"
    gru_path = EVAL_DIR / "gru_benchmark_report.json"
    if not physics_path.exists() or not gru_path.exists():
        pytest.skip("evaluation artifacts not present (run make evaluate / make evaluate-forecast)")

    physics_only = json.loads(physics_path.read_text())
    gru_benchmark = json.loads(gru_path.read_text())

    assert physics_only["n_point_comparisons"] != gru_benchmark["global"]["physics"]["n"], (
        "the broad physics-only evaluation and the GRU benchmark's matched comparison "
        "must be evaluated on different-sized populations -- if they ever match exactly, "
        "verify this isn't an accidental merge of the two harnesses"
    )
    # A different population is free to coincidentally produce a similar MAE, but
    # these two numbers must never be reported as if they were the same measurement.
    assert physics_only["physics_mae_ppm"] != gru_benchmark["global"]["physics"]["mae"]


def test_gru_benchmark_global_improvement_matches_documented_16_8_percent():
    """docs/FINAL_METRICS.md, docs/README.md, docs/ACCEPTANCE_RESULTS.md, and
    docs/REVIEW_PREPARATION.md all quote the GLOBAL hybrid-vs-physics
    improvement as 16.8% (precisely: (57.19429-47.59373)/57.19429 = 16.79%,
    rounds to 16.8%, not the earlier draft's incorrect flat "17%")."""
    path = EVAL_DIR / "gru_benchmark_report.json"
    if not path.exists():
        pytest.skip("models/evaluation/gru_benchmark_report.json not present (run make evaluate-forecast)")

    report = json.loads(path.read_text())
    physics_mae = report["global"]["physics"]["mae"]
    hybrid_mae = report["global"]["hybrid_physics_plus_gru"]["mae"]

    if math.isclose(physics_mae, hybrid_mae, rel_tol=1e-9):
        pytest.skip("GRU artifact unavailable in this environment (torch not installed) -- "
                    "benchmark degraded to physics-only, no improvement to check")

    improvement_pct = (physics_mae - hybrid_mae) / physics_mae * 100
    assert _round1(improvement_pct) == 16.8, (
        f"documented improvement is 16.8%, recomputed {_round1(improvement_pct)}% from "
        f"physics_mae={physics_mae}, hybrid_mae={hybrid_mae} -- update every doc that quotes "
        f"this figure (docs/FINAL_METRICS.md, docs/README.md, docs/ACCEPTANCE_RESULTS.md, "
        f"docs/REVIEW_PREPARATION.md) if this artifact was legitimately regenerated"
    )
    # Sanity: still clears the promotion bar's stated criterion (>=5%).
    assert improvement_pct >= 5.0


def test_gru_benchmark_unannounced_onset_improvement_matches_documented_16_5_percent():
    """The 'unannounced onset' subset (1,062 windows) has its own improvement
    percentage, separate from the global 16.8% -- documented as 16.5%."""
    path = EVAL_DIR / "gru_benchmark_report.json"
    if not path.exists():
        pytest.skip("models/evaluation/gru_benchmark_report.json not present (run make evaluate-forecast)")

    report = json.loads(path.read_text())
    condition = report.get("unannounced_onset_condition")
    if condition is None:
        pytest.skip("unannounced_onset_condition section not present in this artifact version")

    physics_mae = condition["physics"]["mae"]
    hybrid_mae = condition["hybrid_physics_plus_gru"]["mae"]
    if math.isclose(physics_mae, hybrid_mae, rel_tol=1e-9):
        pytest.skip("GRU artifact unavailable in this environment -- degraded to physics-only")

    improvement_pct = (physics_mae - hybrid_mae) / physics_mae * 100
    assert _round1(improvement_pct) == 16.5


def test_physics_only_mae_matches_documented_95_50_ppm():
    """The general/broad physics-only MAE quoted throughout the docs (95.50
    ppm) must keep matching its own source file -- and must never be replaced
    by the unrelated 57.19/47.59 GRU-benchmark figures."""
    path = EVAL_DIR / "physics_forecast_metrics.json"
    if not path.exists():
        pytest.skip("models/evaluation/physics_forecast_metrics.json not present (run make evaluate)")

    metrics = json.loads(path.read_text())
    assert _round1(metrics["physics_mae_ppm"]) == 95.5
    assert metrics["n_scenarios"] == 10
    assert metrics["n_point_comparisons"] == 120
