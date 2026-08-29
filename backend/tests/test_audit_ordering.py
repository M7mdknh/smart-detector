"""Regression test for a bug found live via the guided demo script (Phase 6):
audit events mix two clock bases -- SYSTEM events are stamped with the
simulated event_time, HUMAN actions with real wall-clock time. An
accelerated simulation can put the simulated clock hours ahead of real time
within seconds, so ordering purely by `timestamp` could show a human's
real-time action before the system event it actually followed. `sequence`
(an autoincrementing integer primary key) is the reliable causal order.
"""

from datetime import datetime, timedelta, timezone

from app.contracts.enums import Actor, IncidentAction, IncidentType, Severity
from app.domain.risk.policy import RiskDecision
from app.services import incident_service
from app.storage.models import AuditEventRow


def make_decision():
    return RiskDecision(IncidentType.CO2_ACTION_CROSSING_PREDICTED, Severity.MEDIUM, ["x"], "explanation", "recommendation")


def test_audit_sequence_orders_correctly_even_when_later_event_has_earlier_timestamp(session):
    # SYSTEM opens the incident using a far-future SIMULATED event_time (as an
    # accelerated simulation would produce).
    simulated_now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    row, _ = incident_service.upsert_incident(session, make_decision(), "zone-1", "CO2", None, "GAS_RISK", simulated_now, [])

    # HUMAN acknowledges moments later in REAL wall-clock time, which is
    # chronologically much EARLIER than the simulated timestamp above.
    real_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    incident_service.apply_action(session, row.incident_id, IncidentAction.ACKNOWLEDGE, Actor.HUMAN, "ack", row.version, real_now, "cid-1")

    events = (
        session.query(AuditEventRow)
        .filter(AuditEventRow.incident_id == row.incident_id)
        .order_by(AuditEventRow.sequence)
        .all()
    )
    actions = [e.action for e in events]
    assert actions == ["OPENED", "ACKNOWLEDGE"], "sequence order must reflect true causal order, not the mixed-clock timestamp field"

    # Confirm the timestamps really are out of chronological order (the scenario this
    # bug depends on), proving `sequence`, not `timestamp`, is doing the real work.
    assert events[1].timestamp < events[0].timestamp


def test_sequence_is_globally_monotonic_across_incidents(session):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row_a, _ = incident_service.upsert_incident(session, make_decision(), "zone-1", "CO2", None, "GAS_RISK_A", now, [])
    row_b, _ = incident_service.upsert_incident(session, make_decision(), "zone-1", "CO2", None, "GAS_RISK_B", now + timedelta(seconds=1), [])

    events_a = session.query(AuditEventRow).filter(AuditEventRow.incident_id == row_a.incident_id).all()
    events_b = session.query(AuditEventRow).filter(AuditEventRow.incident_id == row_b.incident_id).all()
    assert events_a[0].sequence < events_b[0].sequence
