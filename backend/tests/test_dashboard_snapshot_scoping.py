"""Regression test for a bug found live during the A05 acceptance pass:
after reloading a scenario, /dashboard/snapshot kept showing the latest
reading/forecast from a PREVIOUS run whose simulated clock had been
accelerated further into the future than the newly-reloaded run's clock
(both queries were unscoped "ORDER BY event_time DESC LIMIT 1" across all
runs ever created for the zone). Calls the route function directly (not
via TestClient) to avoid spinning up the app's full lifespan -- including
the vision worker, which would otherwise try to load a real model.
"""

from app.api.routes import dashboard_snapshot
from app.simulation import engine


def test_snapshot_does_not_leak_stale_future_run_after_reload(session):
    old_run = engine.load_scenario(session, "gradual_leak", seed=42)
    engine.set_controls(session, old_run, source_ppm_m3h=8_000_000, ventilation_m3h=0)
    # Advance the old run's simulated clock far into the future relative to a
    # freshly-loaded run's near-"now" warm start.
    for i in range(70):
        old_run, _ = engine.tick(session, old_run, i)

    old_snapshot = dashboard_snapshot(session)
    old_value = old_snapshot["latest_reading"]["value"]
    assert old_value > 20000  # sanity: the old run really did run far past a normal baseline

    new_run = engine.load_scenario(session, "normal", seed=42)
    new_snapshot = dashboard_snapshot(session)

    assert new_snapshot["simulation"]["run_id"] == new_run.run_id
    assert new_snapshot["latest_reading"] is not None
    assert new_snapshot["latest_reading"]["value"] < 1000, (
        f"dashboard snapshot leaked a stale reading ({new_snapshot['latest_reading']['value']}) "
        f"from the previous run's advanced clock instead of the newly-loaded scenario's warm start"
    )
    assert new_snapshot["forecast"] is not None
    assert new_snapshot["forecast"]["forecast_id"] != old_snapshot["forecast"]["forecast_id"]


def test_snapshot_does_not_leak_stale_reading_on_identical_preset_reload(session):
    """Same as above, but reloading the IDENTICAL preset/seed -- the common case,
    since the default demo always uses seed 42. scenario_id alone can't disambiguate
    two loads of the same preset/seed (they share a scenario_id), so this specifically
    exercises the event_time<=run.event_time bound, not just the scenario_id filter."""
    old_run = engine.load_scenario(session, "gradual_leak", seed=42)
    engine.set_controls(session, old_run, source_ppm_m3h=8_000_000, ventilation_m3h=0)
    for i in range(70):
        old_run, _ = engine.tick(session, old_run, i)

    old_snapshot = dashboard_snapshot(session)
    assert old_snapshot["latest_reading"]["value"] > 20000

    new_run = engine.load_scenario(session, "gradual_leak", seed=42)
    assert new_run.scenario_id == old_run.scenario_id  # same preset/seed -> same scenario_id, deliberately
    new_snapshot = dashboard_snapshot(session)

    assert new_snapshot["latest_reading"]["value"] < 1000, (
        f"dashboard snapshot leaked a stale reading ({new_snapshot['latest_reading']['value']}) "
        f"from an earlier load of the identical preset/seed"
    )
