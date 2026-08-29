"""Interview-demo mode: CV_MODEL-driven incidents and real-frame evidence
capture. Covers the settings-gated exception to the default
SIMULATION_GROUND_TRUTH-only incident policy (app/services/incident_service.py),
the process-local annotated-frame cache (app/inference/frame_cache.py), and
evidence_image.py's real-frame-vs-schematic selection -- all without a GPU
or real video (frame_annotation.render_annotated_frame is exercised with a
synthetic frame + synthetic detections; the model itself is never invoked
here, matching this suite's existing no-GPU-required convention).
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.contracts.enums import IncidentType, Severity
from app.domain.risk.policy import RiskDecision
from app.services import incident_service
from app.storage.models import IncidentEvidenceImageRow, VisionEvidenceRow


def make_decision(itype, severity):
    return RiskDecision(itype, severity, [itype.value], "explanation text", "recommendation text")


# ---------------------------------------------------------------------------
# incident_service._latest_vision_rows: interview_demo_mode gate
# ---------------------------------------------------------------------------


def _add_vision_row(session, now, source: str, zone_id: str = "zone-1", track_id: int = 1, restricted="OUTSIDE"):
    row = VisionEvidenceRow(
        evidence_id=f"ev-{source}-{track_id}", camera_id="camera-1", zone_id=zone_id, frame_id=1,
        event_time=now, ingested_at=now, source=source, model_version="ppe-yolo11n-1.1",
        track_id=track_id, detected_class="person", confidence=0.9,
        bbox_x1=0.1, bbox_y1=0.1, bbox_x2=0.3, bbox_y2=0.9,
        helmet_state="UNKNOWN", vest_state="UNKNOWN",
        gas_zone_membership="UNKNOWN", overhead_zone_membership="UNKNOWN",
        restricted_zone_membership=restricted,
    )
    session.add(row)
    session.commit()
    return row


def test_cv_model_rows_excluded_by_default(session, now):
    _add_vision_row(session, now, "CV_MODEL")
    rows = incident_service._latest_vision_rows(session, "zone-1", now)
    assert rows == []


def test_cv_model_rows_included_when_interview_demo_mode_on(session, now, monkeypatch):
    from app.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(type(settings), "interview_demo_mode", property(lambda self: True), raising=False)

    _add_vision_row(session, now, "CV_MODEL")
    rows = incident_service._latest_vision_rows(session, "zone-1", now)
    assert len(rows) == 1
    assert rows[0].source == "CV_MODEL"


def test_simulation_ground_truth_still_included_when_interview_demo_mode_on(session, now, monkeypatch):
    from app.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(type(settings), "interview_demo_mode", property(lambda self: True), raising=False)

    _add_vision_row(session, now, "SIMULATION_GROUND_TRUTH", track_id=1)
    _add_vision_row(session, now, "CV_MODEL", track_id=2)
    rows = incident_service._latest_vision_rows(session, "zone-1", now)
    assert {r.source for r in rows} == {"SIMULATION_GROUND_TRUTH", "CV_MODEL"}


def test_restricted_zone_incident_can_be_driven_by_cv_model_evidence_in_interview_mode(session, now, monkeypatch):
    from app.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(type(settings), "interview_demo_mode", property(lambda self: True), raising=False)

    _add_vision_row(session, now, "CV_MODEL", restricted="INSIDE")
    from app.storage.models import ForecastRow

    forecast = ForecastRow(
        forecast_id="f1", zone_id="zone-1", gas="CO2", generated_at=now, based_on_event_time=now,
        physics_model_version="physics-1.0", model_status="OK", horizon_minutes=60, step_minutes=5,
        points_json=[{"physics_ppm": 450.0}], crossings_json=[], leak_probability=None, leak_label=None,
    )
    inputs = incident_service.build_risk_inputs(session, forecast, {"current_ppm": 450.0}, "zone-1", now, camera_degraded=False)
    assert inputs.restricted_zone_violation is True


# ---------------------------------------------------------------------------
# frame_cache: bounded, age-aware, process-local
# ---------------------------------------------------------------------------


def test_frame_cache_round_trip_and_expiry():
    from app.inference import frame_cache

    frame_cache.reset_for_tests()
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    frame_cache.set_latest_frame("camera-1", b"jpegbytes", 7, t0)

    got = frame_cache.get_latest_frame("camera-1", t0 + timedelta(seconds=5))
    assert got == (b"jpegbytes", 7, t0)

    # Too old (default max_age_seconds=30) -> None, never a stale frame silently returned.
    stale = frame_cache.get_latest_frame("camera-1", t0 + timedelta(seconds=60))
    assert stale is None

    assert frame_cache.get_latest_frame("camera-does-not-exist", t0) is None


# ---------------------------------------------------------------------------
# frame_annotation: pure rendering, no model/GPU needed
# ---------------------------------------------------------------------------


def test_render_annotated_frame_draws_without_crashing_and_modifies_pixels():
    from app.inference.frame_annotation import render_annotated_frame
    from app.inference.vision_worker_impl import TrackDwell
    from app.inference.zone_config import Zone, ZoneConfig

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    persons = [(1, (0.1, 0.1, 0.3, 0.9), 0.87)]
    ppe_candidates = [("helmet", (0.12, 0.1, 0.28, 0.25), 0.6), ("no_helmet", (0.12, 0.1, 0.28, 0.25), 0.3)]
    tracks = {1: TrackDwell()}
    zone_config = ZoneConfig(version="1.0", camera_id="camera-1", zones=[Zone(id="z1", type="RESTRICTED", label="Restricted zone", points=[(0.3, 0.6), (0.7, 0.6), (0.7, 1.0), (0.3, 1.0)])])

    out = render_annotated_frame(
        frame, persons, ppe_candidates, tracks, zone_config,
        model_version="ppe-yolo11n-1.1", event_time=datetime(2026, 1, 1, tzinfo=timezone.utc), frame_id=42,
        incident_severity_by_track={1: "HIGH"},
    )
    assert out.shape == frame.shape
    assert not np.array_equal(out, frame)  # something was actually drawn


def test_render_annotated_frame_handles_untracked_person():
    from app.inference.frame_annotation import render_annotated_frame
    from app.inference.zone_config import ZoneConfig

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    persons = [(None, (0.1, 0.1, 0.5, 0.9), 0.5)]  # tracker failure: track_id=None
    out = render_annotated_frame(
        frame, persons, [], {}, ZoneConfig(version="1.0", camera_id="c", zones=[]),
        model_version="v", event_time=datetime(2026, 1, 1, tzinfo=timezone.utc), frame_id=1,
    )
    assert out.shape == frame.shape


# ---------------------------------------------------------------------------
# evidence_image: real frame used only for CV_MODEL + interview_demo_mode + cached frame
# ---------------------------------------------------------------------------


def test_evidence_uses_schematic_by_default_even_with_cv_model_row(session, now):
    from app.inference import frame_cache

    frame_cache.reset_for_tests()
    frame_cache.set_latest_frame("camera-1", b"realjpegbytes", 1, now)
    _add_vision_row(session, now, "CV_MODEL", restricted="INSIDE")

    row, created = incident_service.upsert_incident(
        session, make_decision(IncidentType.PERSON_IN_RESTRICTED_ZONE, Severity.HIGH), "zone-1", None, None, "PERSON_IN_RESTRICTED_ZONE", now, []
    )
    img = session.query(IncidentEvidenceImageRow).filter_by(incident_id=row.incident_id).one()
    assert img.is_real_camera_frame is False


def test_evidence_uses_real_frame_when_interview_demo_mode_and_cv_model_and_cached(session, now, monkeypatch):
    from app.inference import frame_cache
    from app.settings import BACKEND_ROOT, get_settings

    settings = get_settings()
    monkeypatch.setattr(type(settings), "interview_demo_mode", property(lambda self: True), raising=False)

    frame_cache.reset_for_tests()
    real_bytes = b"\xff\xd8\xff\xe0genuinejpegbytes"
    frame_cache.set_latest_frame("camera-1", real_bytes, 3, now)
    _add_vision_row(session, now, "CV_MODEL", restricted="INSIDE")

    row, created = incident_service.upsert_incident(
        session, make_decision(IncidentType.PERSON_IN_RESTRICTED_ZONE, Severity.HIGH), "zone-1", None, None, "PERSON_IN_RESTRICTED_ZONE", now, []
    )
    img = session.query(IncidentEvidenceImageRow).filter_by(incident_id=row.incident_id).one()
    assert img.is_real_camera_frame is True
    assert (BACKEND_ROOT / img.file_path).read_bytes() == real_bytes


def test_evidence_falls_back_to_schematic_when_cache_stale(session, now, monkeypatch):
    from app.inference import frame_cache
    from app.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(type(settings), "interview_demo_mode", property(lambda self: True), raising=False)

    frame_cache.reset_for_tests()
    # Cached frame far too old relative to `now` -> must not be silently reused.
    frame_cache.set_latest_frame("camera-1", b"stale", 1, now - timedelta(seconds=120))
    _add_vision_row(session, now, "CV_MODEL", restricted="INSIDE")

    row, created = incident_service.upsert_incident(
        session, make_decision(IncidentType.PERSON_IN_RESTRICTED_ZONE, Severity.HIGH), "zone-1", None, None, "PERSON_IN_RESTRICTED_ZONE", now, []
    )
    img = session.query(IncidentEvidenceImageRow).filter_by(incident_id=row.incident_id).one()
    assert img.is_real_camera_frame is False
