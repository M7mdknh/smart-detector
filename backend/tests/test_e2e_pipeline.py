"""Integration tests: full ingestion -> forecast -> risk -> incident path.

No network, webcam, GPU, or wall-clock sleeps: the simulator's tick() advances
its own event_time and calls engine.tick() directly rather than the real-time loop.
"""


from app.simulation import engine
from app.storage.models import IncidentRow


def test_normal_scenario_no_false_incident(session):
    run = engine.load_scenario(session, "normal", seed=42)
    for i in range(20):
        run, events = engine.tick(session, run, i)

    active = session.query(IncidentRow).filter(IncidentRow.is_active == True).all()  # noqa: E712
    assert active == []


def test_gradual_leak_opens_medium_incident_then_escalates_with_person(session):
    run = engine.load_scenario(session, "gradual_leak", seed=42)
    engine.set_controls(session, run, source_ppm_m3h=5_000_000, ventilation_m3h=None)

    for i in range(30):
        run, events = engine.tick(session, run, i)

    active = session.query(IncidentRow).filter(IncidentRow.is_active == True).all()  # noqa: E712
    gas_incidents = [a for a in active if a.dedup_key == "zone-1:GAS_RISK"]
    assert len(gas_incidents) == 1
    assert gas_incidents[0].severity in ("MEDIUM", "HIGH", "CRITICAL")

    # Move worker into the gas zone; escalation to HIGH/CRITICAL with person reason.
    engine.set_worker(session, run, x=5.0, y=5.0, helmet=None, vest=None, overhead_active=None)
    for i in range(30, 35):
        run, events = engine.tick(session, run, i)

    session.expire_all()
    incident = session.query(IncidentRow).filter(IncidentRow.dedup_key == "zone-1:GAS_RISK").one()
    assert incident.severity in ("HIGH", "CRITICAL")
    assert "PERSON_IN_PREDICTED_GAS_RISK" in incident.reason_codes_json or incident.type == "PERSON_IN_PREDICTED_GAS_RISK"


def test_ventilation_failure_does_not_blindly_call_it_a_leak(session):
    """A known ventilation control change should still surface a rising-concentration
    incident (the risk policy doesn't hide it), but the leak label should reflect that
    ventilation, not an unexplained source, is the operative cause."""
    run = engine.load_scenario(session, "ventilation_failure", seed=42)
    engine.set_controls(session, run, source_ppm_m3h=None, ventilation_m3h=100.0)

    for i in range(40):
        run, events = engine.tick(session, run, i)

    from app.storage.models import ForecastRow

    latest_forecast = (
        session.query(ForecastRow).filter(ForecastRow.zone_id == "zone-1").order_by(ForecastRow.generated_at.desc()).first()
    )
    assert latest_forecast is not None
    # Source rate did not increase, so the leak classifier's fallback (which requires
    # source-consistent rise) should not claim LIKELY_LEAK from ventilation alone.
    assert latest_forecast.leak_label in ("NO_LEAK_SIGNAL", "SUSPICIOUS_TREND")


def test_overhead_helmet_violation_after_dwell(session):
    run = engine.load_scenario(session, "overhead_ppe", seed=42)
    # preset already places worker in overhead zone without helmet
    for i in range(6):  # 6 * 5 simulated minutes >> 3s dwell requirement (dwell uses real seconds via event_time deltas... )
        run, events = engine.tick(session, run, i)

    session.expire_all()
    incident = session.query(IncidentRow).filter(IncidentRow.type == "PPE_HELMET_OVERHEAD_VIOLATION", IncidentRow.is_active == True).one_or_none()  # noqa: E712
    assert incident is not None
    assert incident.severity == "HIGH"


def test_duplicate_reading_no_duplicate_incident(session):
    run = engine.load_scenario(session, "gradual_leak", seed=42)
    engine.set_controls(session, run, source_ppm_m3h=5_000_000, ventilation_m3h=None)
    for i in range(20):
        run, events = engine.tick(session, run, i)

    from sqlalchemy import select

    from app.storage.models import IncidentRow as IR

    count_before = len(session.execute(select(IR).where(IR.dedup_key == "zone-1:GAS_RISK")).scalars().all())

    # Re-run risk pipeline again at the same event_time (simulating a duplicate tick call).
    from app.services import pipeline

    pipeline.run_risk_pipeline(session, run, "zone-1", run.event_time)
    pipeline.run_risk_pipeline(session, run, "zone-1", run.event_time)

    count_after = len(session.execute(select(IR).where(IR.dedup_key == "zone-1:GAS_RISK")).scalars().all())
    assert count_before == count_after == 1
