"""Evidence-image capture: one annotated snapshot per logical incident event
(creation, or a meaningful severity escalation) -- never one per frame -- plus
the safe-by-incident-id retrieval endpoint and the JSON/CSV report endpoints.

Route functions are called directly (not via TestClient/ASGI), matching this
suite's existing convention (see tests/test_dashboard_snapshot_scoping.py) --
avoids spinning up the app's full lifespan including the vision worker.
"""

from datetime import timedelta

import pytest

from app.api.routes import get_incident_evidence, get_incident_report_csv, get_incident_report_json
from app.contracts.enums import IncidentType, Severity
from app.contracts.errors import ApiError
from app.domain.risk.policy import RiskDecision
from app.services import incident_service
from app.settings import BACKEND_ROOT
from app.storage.models import IncidentEvidenceImageRow


def make_decision(itype, severity):
    return RiskDecision(itype, severity, [itype.value], "explanation text", "recommendation text")


def test_evidence_image_created_on_new_ppe_incident(session, now):
    row, created = incident_service.upsert_incident(
        session, make_decision(IncidentType.PPE_HELMET_OVERHEAD_VIOLATION, Severity.HIGH), "zone-1", None, None, "PPE_HELMET_OVERHEAD_VIOLATION", now, []
    )
    assert created is True

    images = session.query(IncidentEvidenceImageRow).filter_by(incident_id=row.incident_id).all()
    assert len(images) == 1
    assert images[0].reason == "CREATED"

    resolved = BACKEND_ROOT / images[0].file_path
    assert resolved.exists()
    assert resolved.stat().st_size > 0


def test_evidence_image_not_duplicated_on_repeated_unchanged_evaluation(session, now):
    decision = make_decision(IncidentType.PPE_VEST_VIOLATION, Severity.MEDIUM)
    row1, _ = incident_service.upsert_incident(session, decision, "zone-1", None, None, "PPE_VEST_VIOLATION", now, [])
    row2, _ = incident_service.upsert_incident(session, decision, "zone-1", None, None, "PPE_VEST_VIOLATION", now, [])
    assert row1.incident_id == row2.incident_id

    images = session.query(IncidentEvidenceImageRow).filter_by(incident_id=row1.incident_id).all()
    assert len(images) == 1  # not one per repeated evaluation/frame


def test_evidence_image_added_again_on_severity_escalation(session, now):
    row1, _ = incident_service.upsert_incident(
        session, make_decision(IncidentType.PERSON_IN_RESTRICTED_ZONE, Severity.HIGH), "zone-1", None, None, "PERSON_IN_RESTRICTED_ZONE", now, []
    )
    images_after_create = session.query(IncidentEvidenceImageRow).filter_by(incident_id=row1.incident_id).all()
    assert len(images_after_create) == 1

    later = now + timedelta(seconds=10)
    row2, _ = incident_service.upsert_incident(
        session, make_decision(IncidentType.PERSON_IN_RESTRICTED_ZONE, Severity.CRITICAL), "zone-1", None, None, "PERSON_IN_RESTRICTED_ZONE", later, []
    )
    assert row2.incident_id == row1.incident_id

    images_after_escalation = (
        session.query(IncidentEvidenceImageRow).filter_by(incident_id=row1.incident_id).order_by(IncidentEvidenceImageRow.created_at).all()
    )
    assert len(images_after_escalation) == 2
    assert images_after_escalation[-1].reason == "SEVERITY_ESCALATED"


def test_no_evidence_image_for_non_eligible_incident_type(session, now):
    """Pure sensor conditions with no tracked person have nothing to depict."""
    row, created = incident_service.upsert_incident(
        session, make_decision(IncidentType.CO2_ACTION_CROSSING_PREDICTED, Severity.MEDIUM), "zone-1", "CO2", 0.4, "GAS_RISK", now, []
    )
    assert created is True
    images = session.query(IncidentEvidenceImageRow).filter_by(incident_id=row.incident_id).all()
    assert images == []


def test_evidence_endpoint_serves_real_file_and_typed_errors(session, now):
    row, _ = incident_service.upsert_incident(
        session, make_decision(IncidentType.PPE_VEST_VIOLATION, Severity.MEDIUM), "zone-1", None, None, "PPE_VEST_VIOLATION", now, []
    )
    from pathlib import Path

    resp = get_incident_evidence(row.incident_id, session)
    assert resp.media_type == "image/jpeg"
    assert Path(resp.path).exists()
    assert Path(resp.path).stat().st_size > 0

    with pytest.raises(ApiError) as exc:
        get_incident_evidence("does-not-exist", session)
    assert exc.value.status_code == 404

    # Incident with no vision-eligible type -> no evidence captured -> typed 404, not a crash.
    row2, _ = incident_service.upsert_incident(
        session, make_decision(IncidentType.CO2_ACTION_CROSSING_PREDICTED, Severity.MEDIUM), "zone-1", "CO2", 0.4, "GAS_RISK", now, []
    )
    with pytest.raises(ApiError) as exc2:
        get_incident_evidence(row2.incident_id, session)
    assert exc2.value.status_code == 404


def test_evidence_endpoint_404_when_file_missing_on_disk(session, now):
    row, _ = incident_service.upsert_incident(
        session, make_decision(IncidentType.PPE_HELMET_OVERHEAD_VIOLATION, Severity.HIGH), "zone-1", None, None, "PPE_HELMET_OVERHEAD_VIOLATION", now, []
    )
    img = session.query(IncidentEvidenceImageRow).filter_by(incident_id=row.incident_id).one()
    (BACKEND_ROOT / img.file_path).unlink()

    with pytest.raises(ApiError) as exc:
        get_incident_evidence(row.incident_id, session)
    assert exc.value.status_code == 404
    assert exc.value.code == "EVIDENCE_FILE_MISSING"


def test_report_json_and_csv_content(session, now):
    row, _ = incident_service.upsert_incident(
        session, make_decision(IncidentType.PPE_VEST_VIOLATION, Severity.MEDIUM), "zone-1", None, None, "PPE_VEST_VIOLATION", now, []
    )
    body = get_incident_report_json(row.incident_id, session)
    assert body["incident_id"] == row.incident_id
    assert body["type"] == "PPE_VEST_VIOLATION"
    assert len(body["evidence_images"]) == 1
    assert body["evidence_images"][0]["reason"] == "CREATED"
    assert "audit_trail" in body and len(body["audit_trail"]) >= 1

    csv_resp = get_incident_report_csv(row.incident_id, session)
    assert csv_resp.media_type == "text/csv"
    text = csv_resp.body.decode("utf-8")
    lines = text.strip().splitlines()
    assert len(lines) == 2  # header + one evidence-image row
    assert row.incident_id in lines[1]
    assert "PPE_VEST_VIOLATION" in lines[1]


def test_report_json_404_for_unknown_incident(session):
    with pytest.raises(ApiError) as exc:
        get_incident_report_json("does-not-exist", session)
    assert exc.value.status_code == 404
