import pytest

from app.contracts.enums import Actor, IncidentAction, IncidentType, Severity
from app.contracts.errors import ApiError
from app.domain.risk.policy import RiskDecision
from app.services import incident_service


def make_decision(itype=IncidentType.CO2_ACTION_CROSSING_PREDICTED, severity=Severity.MEDIUM):
    return RiskDecision(itype, severity, [itype.value], "explanation", "recommendation")


def test_upsert_creates_new_incident(session, now):
    row, created = incident_service.upsert_incident(session, make_decision(), "zone-1", "CO2", 0.5, "GAS_RISK", now, [])
    assert created is True
    assert row.state == "OPEN"
    assert row.version == 1


def test_repeated_evidence_updates_one_incident_not_duplicates(session, now):
    row1, created1 = incident_service.upsert_incident(session, make_decision(), "zone-1", "CO2", 0.5, "GAS_RISK", now, [])
    row2, created2 = incident_service.upsert_incident(session, make_decision(), "zone-1", "CO2", 0.6, "GAS_RISK", now, [])
    assert created1 is True
    assert created2 is False
    assert row1.incident_id == row2.incident_id


def test_repeated_unchanged_evaluation_does_not_bump_version(session, now):
    """Regression: found live via scripts/guided_demo.py -- a manager's ACKNOWLEDGE
    could get a spurious VERSION_CONFLICT 409 because every routine sensor/vision
    re-evaluation cycle bumped `version` even when severity/type were unchanged,
    racing ahead of whatever version the human (or script) had just fetched."""
    row1, _ = incident_service.upsert_incident(session, make_decision(), "zone-1", "CO2", 0.5, "GAS_RISK", now, [])
    version_after_open = row1.version
    for confidence in (0.55, 0.6, 0.65):
        row_n, created_n = incident_service.upsert_incident(session, make_decision(), "zone-1", "CO2", confidence, "GAS_RISK", now, [])
        assert created_n is False
        assert row_n.version == version_after_open, "re-affirming the same decision must not bump the optimistic-concurrency version"

    # A real severity/type change still must bump version so a stale human action is rejected.
    escalated = make_decision(IncidentType.PERSON_IN_PREDICTED_GAS_RISK, Severity.HIGH)
    row_escalated, created_escalated = incident_service.upsert_incident(session, escalated, "zone-1", "CO2", 0.7, "GAS_RISK", now, [])
    assert created_escalated is False
    assert row_escalated.version == version_after_open + 1


def test_incident_evolves_through_severities_without_leaving_stale_incident(session, now):
    low = make_decision(IncidentType.CO2_VENTILATION_ADVISORY, Severity.LOW)
    row1, _ = incident_service.upsert_incident(session, low, "zone-1", "CO2", None, "GAS_RISK", now, [])

    high = make_decision(IncidentType.PERSON_IN_PREDICTED_GAS_RISK, Severity.HIGH)
    row2, created2 = incident_service.upsert_incident(session, high, "zone-1", "CO2", None, "GAS_RISK", now, [])

    assert created2 is False
    assert row1.incident_id == row2.incident_id
    assert row2.severity == "HIGH"
    assert row2.type == IncidentType.PERSON_IN_PREDICTED_GAS_RISK.value


def test_allowed_transition_acknowledge(session, now):
    row, _ = incident_service.upsert_incident(session, make_decision(), "zone-1", "CO2", None, "GAS_RISK", now, [])
    updated = incident_service.apply_action(session, row.incident_id, IncidentAction.ACKNOWLEDGE, Actor.HUMAN, "checking", row.version, now, "cid-1")
    assert updated.state == "ACKNOWLEDGED"
    assert updated.acknowledged_at is not None
    assert updated.version == 2


def test_invalid_transition_rejected(session, now):
    row, _ = incident_service.upsert_incident(session, make_decision(), "zone-1", "CO2", None, "GAS_RISK", now, [])
    with pytest.raises(ApiError) as exc:
        incident_service.apply_action(session, row.incident_id, IncidentAction.INVESTIGATE, Actor.HUMAN, None, row.version, now, "cid-1")
    assert exc.value.code == "INVALID_TRANSITION"
    assert exc.value.status_code == 409


def test_stale_version_rejected(session, now):
    row, _ = incident_service.upsert_incident(session, make_decision(), "zone-1", "CO2", None, "GAS_RISK", now, [])
    stale_version = row.version  # capture as a plain int: `row` is mutated in-place by apply_action below
    incident_service.apply_action(session, row.incident_id, IncidentAction.ACKNOWLEDGE, Actor.HUMAN, None, stale_version, now, "cid-1")
    with pytest.raises(ApiError) as exc:
        incident_service.apply_action(session, row.incident_id, IncidentAction.INVESTIGATE, Actor.HUMAN, None, stale_version, now, "cid-2")
    assert exc.value.code == "VERSION_CONFLICT"
    assert exc.value.status_code == 409


def test_full_workflow_and_audit_trail(session, now):
    row, _ = incident_service.upsert_incident(session, make_decision(), "zone-1", "CO2", None, "GAS_RISK", now, [])
    row = incident_service.apply_action(session, row.incident_id, IncidentAction.ACKNOWLEDGE, Actor.HUMAN, "c1", row.version, now, "cid-1")
    row = incident_service.apply_action(session, row.incident_id, IncidentAction.INVESTIGATE, Actor.HUMAN, "c2", row.version, now, "cid-2")
    row = incident_service.apply_action(session, row.incident_id, IncidentAction.RESOLVE, Actor.HUMAN, "c3", row.version, now, "cid-3")
    assert row.state == "RESOLVED"
    assert row.is_active is False
    assert row.resolved_at is not None

    from sqlalchemy import select

    from app.storage.models import AuditEventRow

    events = session.execute(select(AuditEventRow).where(AuditEventRow.incident_id == row.incident_id).order_by(AuditEventRow.timestamp)).scalars().all()
    actions = [e.action for e in events]
    assert actions == ["OPENED", "ACKNOWLEDGE", "INVESTIGATE", "RESOLVE"]


def test_open_to_resolved_direct_transition_allowed(session, now):
    row, _ = incident_service.upsert_incident(session, make_decision(), "zone-1", "CO2", None, "GAS_RISK", now, [])
    updated = incident_service.apply_action(session, row.incident_id, IncidentAction.RESOLVE, Actor.HUMAN, None, row.version, now, "cid-1")
    assert updated.state == "RESOLVED"
