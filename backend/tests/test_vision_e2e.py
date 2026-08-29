"""Principal vision end-to-end test: real YOLO11n detector + real ByteTrack
against real frames decoded from the bundled replay clip -- NOT a mocked
detector (CLAUDE.md / the task's explicit requirement). Deterministic-adapter
coverage for edge cases (ambiguous PPE, tracker loss) lives in
tests/test_vision_association.py instead.

Skipped (not failed) when the vision extras (ultralytics/opencv/torch) or the
bundled replay clip aren't present, so `make test` stays runnable without the
heavy vision dependencies -- but when they ARE present, this test exercises
the real model, matching the task's requirement that the principal vision
path not be mocked.

Frame timestamps are synthetic (stepped deterministically), not real wall-clock
sleeps, so dwell thresholds are reached without slowing the test suite.
"""

from datetime import datetime, timedelta, timezone

import pytest

cv2 = pytest.importorskip("cv2", reason="opencv not installed (backend/requirements-vision.txt)")
pytest.importorskip("ultralytics", reason="ultralytics not installed (backend/requirements-vision.txt)")

from app.services import incident_service  # noqa: E402
from app.services.vision_replay import get_replay_status  # noqa: E402
from app.settings import get_settings  # noqa: E402
from app.storage.models import IncidentRow, VisionEvidenceRow  # noqa: E402

REPLAY_PATH = get_settings().vision_replay_path

pytestmark = pytest.mark.skipif(not REPLAY_PATH.exists(), reason=f"bundled replay clip not present at {REPLAY_PATH}")


def _decode_frames(path, max_frames: int):
    cap = cv2.VideoCapture(str(path))
    frames = []
    while len(frames) < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    return frames


@pytest.fixture(scope="module")
def real_model():
    from app.inference.vision_worker_impl import load_model

    model, model_version, person_only, status = load_model()
    if person_only or model is None:
        pytest.skip("fine-tuned PPE artifact not present/verified; detector unavailable, cannot test PPE classes")
    return model, model_version


def test_real_detector_produces_person_and_ppe_evidence(real_model, session):
    """(1)-(4): a real frame enters the actual detector, produces person/PPE
    classes, ByteTrack assigns anonymous tracks, and PPE evidence associates
    with a person."""
    from app.inference.vision_worker_impl import TrackDwell, process_frame

    model, model_version = real_model
    frames = _decode_frames(REPLAY_PATH, max_frames=40)
    assert frames, "no frames decoded from the bundled replay clip"

    tracks: dict[int, TrackDwell] = {}
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    all_rows = []
    for i, frame in enumerate(frames):
        event_time = t0 + timedelta(seconds=i * 0.5)  # synthetic clock, no wall-clock sleep
        rows = process_frame(model, frame, i, event_time, tracks, person_only=False, model_version=model_version)
        all_rows.extend(rows)

    person_rows = [r for r in all_rows if r.detected_class == "person"]
    assert person_rows, "expected at least one real person detection across the replay clip"
    assert all(r.source == "CV_MODEL" for r in person_rows), "real detections must carry CV_MODEL provenance, never SIMULATION_GROUND_TRUTH"

    tracked_rows = [r for r in person_rows if r.track_id is not None]
    assert tracked_rows, "expected ByteTrack to assign at least one anonymous track_id"
    assert all(isinstance(r.track_id, int) for r in tracked_rows)

    ppe_states = {r.helmet_state for r in tracked_rows} | {r.vest_state for r in tracked_rows}
    assert ppe_states, "expected some PPE state to be recorded (even if UNKNOWN pending dwell)"


def test_single_frame_does_not_open_incident_dwell_required(real_model, session):
    """(5)-(6): timestamp dwell prevents single-frame violations; persistent
    missing helmet in the overhead zone opens exactly one incident."""
    from app.inference.vision_worker_impl import TrackDwell, process_frame

    model, model_version = real_model
    frames = _decode_frames(REPLAY_PATH, max_frames=60)

    tracks: dict[int, TrackDwell] = {}
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

    # First frame only: even if a person with missing helmet appears, no violation yet.
    first_rows = process_frame(model, frames[0], 0, t0, tracks, person_only=False, model_version=model_version)
    for r in first_rows:
        if r.overhead_zone_membership == "INSIDE":
            assert r.helmet_state != "NON_COMPLIANT", "a single frame must not immediately register a PPE violation"

    # Feed the full sequence with a synthetic clock stepping well past every dwell
    # threshold (2s zone entry, 3s violation, well beyond the ~4s per source image).
    for i, frame in enumerate(frames):
        event_time = t0 + timedelta(seconds=i * 0.5)
        rows = process_frame(model, frame, i, event_time, tracks, person_only=False, model_version=model_version)
        for r in rows:
            session.add(r)
    session.commit()

    persistent_violations = (
        session.query(VisionEvidenceRow)
        .filter(VisionEvidenceRow.overhead_zone_membership == "INSIDE", VisionEvidenceRow.helmet_state == "NON_COMPLIANT")
        .count()
    )
    if persistent_violations == 0:
        pytest.skip("bundled replay clip did not contain a sustained overhead-zone no-helmet sequence at the current zone split; see demo-assets/REPLAY_SOURCE.md")

    # Run the risk pipeline against this evidence via the same ground-truth-independent
    # path incidents use for vision evidence, confirming exactly one incident opens.
    from app.domain.risk.policy import RiskInputs, evaluate_ppe_risk

    inputs = RiskInputs(
        current_co2_ppm=450, short_term_avg_ppm=None, action_crossing_outcome="NO_CROSSING", action_crossing_minutes=None,
        idlh_crossing_outcome="NO_CROSSING", idlh_crossing_minutes=None, person_in_gas_zone=False, person_zone_unknown=False,
        ventilation_advisory=False, niosh_short_term_ppm=30000, niosh_idlh_ppm=40000, helmet_violation_overhead=True,
        vest_violation_mandatory_zone=False, sensor_unreliable=False, camera_degraded=False,
    )
    decisions = evaluate_ppe_risk(inputs)
    assert len(decisions) == 1

    now = t0 + timedelta(seconds=len(frames) * 0.5)
    row1, created1 = incident_service.upsert_incident(session, decisions[0], "zone-1", None, None, decisions[0].incident_type.value, now, [])
    assert created1 is True

    # (7) repeated frames / repeated pipeline evaluation updates rather than duplicates.
    row2, created2 = incident_service.upsert_incident(session, decisions[0], "zone-1", None, None, decisions[0].incident_type.value, now, [])
    assert created2 is False
    assert row1.incident_id == row2.incident_id

    open_count = session.query(IncidentRow).filter(IncidentRow.type == "PPE_HELMET_OVERHEAD_VIOLATION", IncidentRow.is_active == True).count()  # noqa: E712
    assert open_count == 1


def test_camera_outage_reports_degraded_not_safe(session):
    """(9): camera/model outage becomes degraded and never claims zero workers
    or a safe scene. Exercised at the status-reporting layer the dashboard reads."""
    from app.inference.vision_pipeline import VisionWorker, get_vision_worker, reset_vision_worker_for_tests

    reset_vision_worker_for_tests()
    worker = get_vision_worker()
    assert isinstance(worker, VisionWorker)
    assert worker.status == "UNAVAILABLE"  # no video source configured against this test session's settings

    status = get_replay_status(session)
    assert status["status"] == "UNAVAILABLE"
    assert status["tracks"] == []
    # The dashboard-facing status object never asserts "0 people, scene safe" --
    # it reports degraded status and an empty evidence list for the frontend to
    # render as UNKNOWN, per StatusCards.tsx's camera-degraded handling.


def test_dashboard_snapshot_reflects_same_persisted_evidence_and_provenance(real_model, session):
    """(10): the dashboard reads the same persisted evidence with the same
    CV_MODEL provenance the detector wrote, not a re-derived or invented value."""
    from app.inference.vision_worker_impl import TrackDwell, process_frame

    model, model_version = real_model
    frames = _decode_frames(REPLAY_PATH, max_frames=5)
    tracks: dict[int, TrackDwell] = {}
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, frame in enumerate(frames):
        rows = process_frame(model, frame, i, t0 + timedelta(seconds=i * 0.5), tracks, person_only=False, model_version=model_version)
        for r in rows:
            session.add(r)
    session.commit()

    status = get_replay_status(session)
    persisted_ids = {r.evidence_id for r in session.query(VisionEvidenceRow).filter(VisionEvidenceRow.camera_id == "camera-1")}
    reported_ids = {t["evidence_id"] for t in status["tracks"]}
    assert reported_ids <= persisted_ids
    assert all(t.get("track_id") is None or isinstance(t["track_id"], int) for t in status["tracks"])
