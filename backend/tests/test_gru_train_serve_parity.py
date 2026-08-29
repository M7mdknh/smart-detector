"""Train/serve parity audit for the physics-informed residual GRU (Phase 4).

CLAUDE.md requires the GRU's runtime behavior to match how it was trained
(same feature names/order, same normalization, same history length, same
control-state semantics) or any deliberate difference to be documented.

This test builds one synthetic scenario, runs it through BOTH:
  - the offline training-time windowing path (app.inference.gru_dataset.build_windows_for_scenario),
  - the live serve-time feature builder (app.services.forecast_service._build_gru_feature_window),
for the same 120-step window, and compares the resulting (120, 7) feature
arrays element-by-element.

Known, already-documented difference (see forecast_service.py's docstring):
live inference holds ventilation/source constant at their CURRENT run value
across the whole lookback window, whereas training uses the true historical
per-tick control values. This test uses a scenario with CONSTANT
ventilation/source throughout, which neutralizes that documented skew, in
order to isolate whether anything else differs.

Under that constant-control setup, this test found one additional,
previously undocumented discrepancy: the "physics_one_step" causal chain
(and therefore the residual channel derived from it) is seeded from
`run.inlet_co2_ppm` at serve time for the FIRST row of the window, whereas
offline training seeds it from the true observed reading immediately
preceding the window (because the offline series is computed once over the
whole scenario, then sliced). Serve time cannot see that preceding reading
because `_lookback_readings` only fetches the window itself. This makes row
0 of the (120, 7) feature window differ between train and serve on columns
1 (`physics_one_step_norm`) and 2 (`residual_norm`) whenever the reading
immediately before the window differs from the inlet baseline (450 ppm) --
which is the common case for any window that isn't the very first one in a
scenario. Rows 1-119 are unaffected (both paths chain from the same
in-window observed values from there on), and physics itself -- the
authoritative forecast/crossing path -- is entirely unaffected; this only
changes the size of the optional GRU residual correction for a fraction of
one 5-minute input step.

This test documents and asserts that exact, narrow difference rather than
asserting full equality, so a regression that *widens* the mismatch (e.g. to
more rows, or to the control columns) will fail the test.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np

from app.inference import gru_dataset
from app.inference.synthetic_scenarios import ScenarioSpec, generate_scenario_dataframe
from app.services.forecast_service import _build_gru_feature_window


def _constant_control_scenario() -> tuple:
    """A scenario long enough to contain a second (non-first) 120-step window,
    with ventilation/source held constant throughout so the documented
    control-held-constant serve-time skew cannot contribute to any observed
    difference here."""
    spec = ScenarioSpec(scenario_id="parity-test-1", seed=4242, kind="ventilation_change", duration_hours=20.0)
    df = generate_scenario_dataframe(spec)
    # Force constant controls so only the windowing/seeding logic is under test.
    df["ventilation_m3h"] = 500.0
    df["source_ppm_m3h"] = 0.0
    return spec, df


def test_feature_names_and_shape_contract_match():
    """The serve-time builder hardcodes 7 columns; assert it still matches the
    canonical, versioned FEATURE_NAMES list rather than silently drifting."""
    assert len(gru_dataset.FEATURE_NAMES) == 7
    assert gru_dataset.FEATURE_NAMES == [
        "observed_co2_norm",
        "physics_one_step_norm",
        "residual_norm",
        "ventilation_norm",
        "source_norm",
        "missing_mask",
        "quality_flag",
    ]


def test_offline_and_serve_feature_windows_match_except_documented_seed_row():
    spec, df = _constant_control_scenario()
    windows = gru_dataset.build_windows_for_scenario(df, spec.scenario_id)
    assert len(windows) >= 2, "need at least two windows to get one that is not the scenario's first"

    # Use the SECOND window: its input_start_idx > 0, so offline physics_one_step[0]
    # for this window was seeded from a real preceding observed reading, not INLET_PPM.
    window = windows[1]
    cutoff_idx = int(round(window.cutoff_minute / gru_dataset.STEP_MINUTES))
    input_start_idx = cutoff_idx - gru_dataset.INPUT_STEPS
    assert input_start_idx > 0

    # Build the equivalent serve-time input: the same 120 rows, as SensorReadingRow-like
    # objects, fed through forecast_service's live feature builder.
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    window_df = df.iloc[input_start_idx:cutoff_idx]
    readings = [
        SimpleNamespace(
            value=float(row.ppm),
            quality="MISSING" if row.missing else "GOOD",
            event_time=base_time + timedelta(minutes=float(row.minute)),
            zone_id="zone-1",
        )
        for row in window_df.itertuples()
    ]
    run = SimpleNamespace(
        ventilation_m3_per_h=500.0,
        source_ppm_m3_per_h=0.0,
        zone_volume_m3=gru_dataset.VOLUME_M3,
        inlet_co2_ppm=gru_dataset.INLET_PPM,
    )

    serve_X = _build_gru_feature_window(readings, run)
    assert serve_X is not None
    assert serve_X.shape == window.X.shape == (gru_dataset.INPUT_STEPS, len(gru_dataset.FEATURE_NAMES))

    offline_X = window.X

    # Columns 0 (observed), 3 (ventilation), 4 (source), 5 (missing_mask), 6
    # (quality_flag) must match exactly on every row -- these do not depend on
    # any cross-window physics chaining.
    for col in (0, 3, 4, 5, 6):
        np.testing.assert_allclose(
            serve_X[:, col], offline_X[:, col], atol=1e-9,
            err_msg=f"feature column {gru_dataset.FEATURE_NAMES[col]} unexpectedly diverged between train and serve",
        )

    # Columns 1 (physics_one_step) and 2 (residual) must match on every row
    # EXCEPT row 0, where serve seeds the causal chain from run.inlet_co2_ppm
    # instead of the true preceding observed reading.
    for col in (1, 2):
        np.testing.assert_allclose(
            serve_X[1:, col], offline_X[1:, col], atol=1e-9,
            err_msg=f"feature column {gru_dataset.FEATURE_NAMES[col]} diverged beyond the documented row-0 seed difference",
        )

    row0_differs = not np.allclose(serve_X[0, [1, 2]], offline_X[0, [1, 2]], atol=1e-9)
    preceding_reading_ppm = float(df.iloc[input_start_idx - 1]["ppm"])
    if abs(preceding_reading_ppm - gru_dataset.INLET_PPM) > 1e-6:
        assert row0_differs, (
            "expected the documented row-0 physics_one_step/residual seed mismatch "
            "(serve uses inlet_co2_ppm, training uses the true preceding reading); "
            "if this now passes, the seeding discrepancy may have been fixed -- "
            "update forecast_service.py's docstring and docs/README.md's GRU section accordingly"
        )


def test_first_window_of_a_scenario_has_no_seed_mismatch():
    """Sanity check on the mechanism above: for the scenario's very FIRST window
    (input_start_idx == 0), both offline and serve seed physics_one_step[0] from
    the same inlet baseline, so row 0 should match too."""
    spec, df = _constant_control_scenario()
    windows = gru_dataset.build_windows_for_scenario(df, spec.scenario_id)
    window = windows[0]
    cutoff_idx = int(round(window.cutoff_minute / gru_dataset.STEP_MINUTES))
    input_start_idx = cutoff_idx - gru_dataset.INPUT_STEPS
    assert input_start_idx == 0

    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    window_df = df.iloc[input_start_idx:cutoff_idx]
    readings = [
        SimpleNamespace(
            value=float(row.ppm),
            quality="MISSING" if row.missing else "GOOD",
            event_time=base_time + timedelta(minutes=float(row.minute)),
            zone_id="zone-1",
        )
        for row in window_df.itertuples()
    ]
    run = SimpleNamespace(
        ventilation_m3_per_h=500.0,
        source_ppm_m3_per_h=0.0,
        zone_volume_m3=gru_dataset.VOLUME_M3,
        inlet_co2_ppm=gru_dataset.INLET_PPM,
    )
    serve_X = _build_gru_feature_window(readings, run)
    np.testing.assert_allclose(serve_X, window.X, atol=1e-9)
