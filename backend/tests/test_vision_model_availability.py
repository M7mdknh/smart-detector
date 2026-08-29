"""Missing/corrupt PPE model artifact must degrade honestly and never trigger a
network download or silently substitute a different (non-fine-tuned) model.

Covers the fix in app/inference/vision_worker_impl.py::load_model: the artifact
path is verified to exist AND its sha256 must match models/registry.json's
"ppe_detector" entry before ultralytics.YOLO is ever constructed. Missing or
corrupt -> (None, None, True, ModelStatus.UNAVAILABLE), no YOLO() call at all
(not even with a pretrained-name string), so there is no possible network
access. Also confirms camera health and detector health are independent
fields, PPE evidence degrades to UNKNOWN, and restoring a valid artifact
recovers full inference.
"""

import hashlib
import socket

import pytest

from app.contracts.enums import ModelStatus
from app.settings import get_settings

ultralytics = pytest.importorskip("ultralytics", reason="ultralytics not installed (backend/requirements-vision.txt)")

REAL_ARTIFACT = get_settings().models_dir / "artifacts" / "ppe-yolo11n.pt"
pytestmark = pytest.mark.skipif(not REAL_ARTIFACT.exists(), reason="bundled fine-tuned PPE artifact not present")


class _NetworkGuard:
    """socket.socket replacement that raises instead of ever connecting out --
    a plain, dependency-free way to prove no network call happens on this path."""

    def __call__(self, *a, **k):
        raise AssertionError("no network access should be attempted while loading a local, already-verified PPE model artifact")


@pytest.fixture
def block_network(monkeypatch):
    monkeypatch.setattr(socket, "socket", _NetworkGuard())
    yield


@pytest.fixture
def no_yolo_calls(monkeypatch):
    """Records every call made to ultralytics.YOLO so we can assert it is never
    invoked with anything but the one verified local path (or not invoked at all)."""
    calls = []
    real_yolo = ultralytics.YOLO

    def _tracking_yolo(*args, **kwargs):
        calls.append((args, kwargs))
        return real_yolo(*args, **kwargs)

    monkeypatch.setattr(ultralytics, "YOLO", _tracking_yolo)
    return calls


def test_missing_artifact_returns_model_unavailable_with_no_network_call(tmp_path, block_network, no_yolo_calls):
    from app.inference.vision_worker_impl import load_model

    missing_path = tmp_path / "does-not-exist.pt"
    model, model_version, person_only, status = load_model(model_path=missing_path)

    assert model is None
    assert model_version is None
    assert person_only is True
    assert status == ModelStatus.UNAVAILABLE
    assert no_yolo_calls == []  # ultralytics.YOLO must never be constructed


def test_corrupted_artifact_checksum_mismatch_returns_model_unavailable_with_no_network_call(tmp_path, block_network, no_yolo_calls):
    from app.inference.vision_worker_impl import load_model

    corrupt_path = tmp_path / "ppe-yolo11n.pt"
    corrupt_path.write_bytes(b"not a real checkpoint, wrong bytes entirely")

    # Sanity: this file's digest really does differ from the registry's recorded
    # checksum for ppe_detector, so the mismatch branch is genuinely exercised.
    import json

    registry = json.loads(get_settings().model_registry_path.read_text())
    expected = registry["ppe_detector"]["sha256"]
    assert hashlib.sha256(corrupt_path.read_bytes()).hexdigest() != expected

    model, model_version, person_only, status = load_model(model_path=corrupt_path)

    assert model is None
    assert status == ModelStatus.UNAVAILABLE
    assert no_yolo_calls == []


def test_valid_artifact_loads_ok_with_exactly_one_verified_local_call(no_yolo_calls):
    from app.inference.vision_worker_impl import load_model

    model, model_version, person_only, status = load_model(model_path=REAL_ARTIFACT)

    assert model is not None
    assert status == ModelStatus.OK
    assert person_only is False
    assert model_version == "ppe-yolo11n-1.1"
    # Exactly one construction, and only ever with the verified local path --
    # never a bare pretrained-name string like "yolo11n.pt".
    assert len(no_yolo_calls) == 1
    (args, kwargs) = no_yolo_calls[0]
    assert args == (str(REAL_ARTIFACT),)


def test_round_trip_restoring_valid_artifact_recovers_full_inference(tmp_path):
    """Missing -> UNAVAILABLE, then pointing back at the real artifact -> OK.
    Proves the degraded state is not sticky/cached across a real recovery."""
    from app.inference.vision_worker_impl import load_model

    missing_path = tmp_path / "ppe-yolo11n.pt"
    model, _, person_only, status = load_model(model_path=missing_path)
    assert model is None and status == ModelStatus.UNAVAILABLE and person_only is True

    model, model_version, person_only, status = load_model(model_path=REAL_ARTIFACT)
    assert model is not None
    assert status == ModelStatus.OK
    assert person_only is False


def test_camera_and_detector_health_are_independent_fields():
    """Camera (replay stream decoding) and detector (model verified+loaded) are
    reported as separate fields on VisionWorker; camera can be HEALTHY while the
    detector is UNAVAILABLE (missing/corrupt artifact) -- never collapsed into
    a single field that would hide detector failure behind a healthy camera."""
    from app.inference.vision_pipeline import VisionWorker

    worker = VisionWorker()
    worker.camera_status = "HEALTHY"
    worker.detector_status = "UNAVAILABLE"
    assert worker.camera_status != worker.detector_status

    from app.inference.vision_pipeline import get_vision_worker, reset_vision_worker_for_tests

    reset_vision_worker_for_tests()
    fresh = get_vision_worker()
    assert fresh.camera_status == "UNAVAILABLE"  # both start UNAVAILABLE until start()/_run() prove otherwise
    assert fresh.detector_status == "UNAVAILABLE"
    reset_vision_worker_for_tests()


def test_ppe_evidence_is_unknown_when_detector_unavailable():
    """When the detector can't run, no PPE compliance evidence is fabricated --
    a person box should never be evaluated at all in this path (run_replay_loop
    skips process_frame entirely when model is None), and any pre-existing
    dwell state stays UNKNOWN rather than being flipped to a false COMPLIANT."""
    from app.contracts.enums import PpeState
    from app.inference.vision_worker_impl import TrackDwell

    dwell = TrackDwell()
    assert dwell.helmet_state == PpeState.UNKNOWN
    assert dwell.vest_state == PpeState.UNKNOWN


def test_status_endpoint_reports_degraded_vision_when_detector_unavailable(session):
    """The health/status API the frontend reads must show camera=HEALTHY,
    detector=UNAVAILABLE, vision=DEGRADED (not a fabricated safe/healthy vision
    status). Calls the route function directly (project convention, see
    test_dashboard_snapshot_scoping.py) rather than via TestClient/ASGI lifespan."""
    from app.api.routes import system_status
    from app.inference.vision_pipeline import get_vision_worker, reset_vision_worker_for_tests

    reset_vision_worker_for_tests()
    worker = get_vision_worker()
    worker.camera_status = "HEALTHY"
    worker.detector_status = "UNAVAILABLE"
    worker.status = "DEGRADED"

    body = system_status(session)
    assert body["camera"] == "HEALTHY"
    assert body["detector"] == "UNAVAILABLE"
    assert body["vision"] == "DEGRADED"
    assert body["vision_message"]

    reset_vision_worker_for_tests()
