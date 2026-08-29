"""Regression tests for the v1.2 PPE-detector candidate/promotion machinery:

  - registry-driven default artifact selection in load_model (the mechanism
    that lets a promotion switch the active model via models/registry.json
    alone, without overwriting any artifact file on disk);
  - candidate-vs-active artifact separation (an explicit model_path override
    that does NOT match the registry's active sha256 must never borrow the
    active version's label, and must never be treated as verified);
  - the promotion-gate pass/fail decision logic in scripts/promote_vision_v1_2.py,
    exercised against synthetic comparative-evaluation fixtures (no GPU/training
    required -- these are pure decision-logic unit tests);
  - the promote() function's registry-write and artifact-copy behavior on a
    pass, and its refusal to touch the registry or v1.1's artifact on a
    missing-candidate error.
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# load_model: registry-driven default artifact selection / candidate separation
# ---------------------------------------------------------------------------


def _write_fake_registry(path: Path, artifact_filename: str, sha256: str, version: str = "1.1"):
    path.write_text(json.dumps({
        "ppe_detector": {
            "version": version,
            "artifact_path": f"models/artifacts/{artifact_filename}",
            "sha256": sha256,
        }
    }))


def test_load_model_default_path_follows_registry_artifact_pointer(tmp_path, monkeypatch):
    """With no model_path override, load_model must resolve the artifact
    filename from registry.json's ppe_detector.artifact_path field -- not a
    hardcoded literal -- so a promotion can switch the active model purely by
    editing the registry, never by overwriting a file."""
    pytest.importorskip("ultralytics", reason="ultralytics not installed (backend/requirements-vision.txt)")
    from app.inference import vision_worker_impl as m
    from app.contracts.enums import ModelStatus

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    fake_weights = artifacts_dir / "ppe-yolo11n-v1.2.pt"
    fake_weights.write_bytes(b"pretend-checkpoint-bytes-v1.2")
    digest = hashlib.sha256(fake_weights.read_bytes()).hexdigest()

    registry_path = tmp_path / "registry.json"
    _write_fake_registry(registry_path, "ppe-yolo11n-v1.2.pt", digest, version="1.2")

    settings = m.get_settings()
    monkeypatch.setattr(type(settings), "models_dir", property(lambda self: tmp_path), raising=False)
    monkeypatch.setattr(type(settings), "model_registry_path", property(lambda self: registry_path), raising=False)

    calls = []

    class _FakeYOLO:
        def __init__(self, path):
            calls.append(path)
            self.names = {}

    monkeypatch.setattr(m, "YOLO", _FakeYOLO, raising=False)
    import ultralytics
    monkeypatch.setattr(ultralytics, "YOLO", _FakeYOLO)

    model, model_version, person_only, status = m.load_model()

    assert status == ModelStatus.OK
    assert person_only is False
    assert model_version == "ppe-yolo11n-1.2"  # registry version label, only because sha256 matched
    assert calls == [str(fake_weights)]


def test_load_model_explicit_override_not_matching_active_registry_is_labelled_from_filename(tmp_path, monkeypatch):
    """Evaluating an unpromoted CANDIDATE (explicit model_path, registry still
    points at v1.1) must not borrow the registry's active version label --
    it should be labelled from its own filename, proving candidate and active
    artifacts are never conflated."""
    pytest.importorskip("ultralytics", reason="ultralytics not installed (backend/requirements-vision.txt)")
    from app.inference import vision_worker_impl as m
    from app.contracts.enums import ModelStatus

    active_weights = tmp_path / "ppe-yolo11n.pt"
    active_weights.write_bytes(b"active-v1.1-bytes")
    active_digest = hashlib.sha256(active_weights.read_bytes()).hexdigest()

    candidate_weights = tmp_path / "ppe-yolo11n-v1.2-epoch7-candidate.pt"
    candidate_weights.write_bytes(b"candidate-v1.2-bytes-different")

    registry_path = tmp_path / "registry.json"
    _write_fake_registry(registry_path, "ppe-yolo11n.pt", active_digest, version="1.1")

    settings = m.get_settings()
    monkeypatch.setattr(type(settings), "models_dir", property(lambda self: tmp_path), raising=False)
    monkeypatch.setattr(type(settings), "model_registry_path", property(lambda self: registry_path), raising=False)

    class _FakeYOLO:
        def __init__(self, path):
            self.names = {}

    import ultralytics
    monkeypatch.setattr(ultralytics, "YOLO", _FakeYOLO)

    model, model_version, person_only, status = m.load_model(model_path=candidate_weights)

    assert status == ModelStatus.OK
    assert model_version == "ppe-yolo11n-v1.2-epoch7-candidate"  # filename-derived, not "ppe-yolo11n-1.1"


def test_load_model_registry_pointing_at_missing_candidate_degrades_honestly(tmp_path, monkeypatch):
    from app.inference import vision_worker_impl as m
    from app.contracts.enums import ModelStatus

    registry_path = tmp_path / "registry.json"
    _write_fake_registry(registry_path, "ppe-yolo11n-v1.2.pt", "0" * 64, version="1.2")  # file never created

    settings = m.get_settings()
    monkeypatch.setattr(type(settings), "models_dir", property(lambda self: tmp_path), raising=False)
    monkeypatch.setattr(type(settings), "model_registry_path", property(lambda self: registry_path), raising=False)

    model, model_version, person_only, status = m.load_model()

    assert model is None
    assert person_only is True
    assert status == ModelStatus.UNAVAILABLE


def test_load_model_registry_pointing_at_checksum_mismatched_candidate_degrades_honestly(tmp_path, monkeypatch):
    from app.inference import vision_worker_impl as m
    from app.contracts.enums import ModelStatus

    artifact = tmp_path / "ppe-yolo11n-v1.2.pt"
    artifact.write_bytes(b"some bytes that will not match the registered checksum")

    registry_path = tmp_path / "registry.json"
    _write_fake_registry(registry_path, "ppe-yolo11n-v1.2.pt", "f" * 64, version="1.2")

    settings = m.get_settings()
    monkeypatch.setattr(type(settings), "models_dir", property(lambda self: tmp_path), raising=False)
    monkeypatch.setattr(type(settings), "model_registry_path", property(lambda self: registry_path), raising=False)

    model, model_version, person_only, status = m.load_model()

    assert model is None
    assert status == ModelStatus.UNAVAILABLE


# ---------------------------------------------------------------------------
# promote_vision_v1_2: gate decision logic (pure, no GPU/training needed)
# ---------------------------------------------------------------------------


def _fake_report(v11_no_helmet_recall, v12_no_helmet_recall, v11_no_helmet_precision=0.5, v12_no_helmet_precision=0.5, regress=False):
    def per_class(no_helmet_recall, no_helmet_precision, other_recall=0.8):
        return {
            "person": {"recall": other_recall, "precision": 0.8},
            "helmet": {"recall": other_recall, "precision": 0.8},
            "vest": {"recall": other_recall, "precision": 0.8},
            "no_helmet": {"recall": no_helmet_recall, "precision": no_helmet_precision},
        }

    v12_other_recall = 0.5 if regress else 0.8
    return {
        "v1_1_active": {
            "source_1_construction_ppe_test_split": {"per_class": per_class(v11_no_helmet_recall, v11_no_helmet_precision)},
            "source_2_industrial_safety_test_split": {"per_class": per_class(v11_no_helmet_recall, v11_no_helmet_precision)},
        },
        "v1_2_candidate": {
            "source_1_construction_ppe_test_split": {"per_class": per_class(v12_no_helmet_recall, v12_no_helmet_precision, v12_other_recall)},
            "source_2_industrial_safety_test_split": {"per_class": per_class(v12_no_helmet_recall, v12_no_helmet_precision, v12_other_recall)},
        },
    }


def test_gate_passes_on_clear_improvement():
    import promote_vision_v1_2 as p

    report = _fake_report(v11_no_helmet_recall=0.175, v12_no_helmet_recall=0.45, v11_no_helmet_precision=0.4, v12_no_helmet_precision=0.4)
    gate = p.evaluate_gate(report)
    assert gate["overall_pass"] is True
    assert gate["checks"]["no_helmet_recall_improves"]["pass"] is True


def test_gate_fails_when_no_helmet_recall_does_not_improve():
    import promote_vision_v1_2 as p

    report = _fake_report(v11_no_helmet_recall=0.175, v12_no_helmet_recall=0.10)
    gate = p.evaluate_gate(report)
    assert gate["overall_pass"] is False
    assert gate["checks"]["no_helmet_recall_improves"]["pass"] is False


def test_gate_fails_when_precision_collapses():
    import promote_vision_v1_2 as p

    report = _fake_report(v11_no_helmet_recall=0.175, v12_no_helmet_recall=0.9, v11_no_helmet_precision=0.4, v12_no_helmet_precision=0.01)
    gate = p.evaluate_gate(report)
    assert gate["overall_pass"] is False
    assert gate["checks"]["no_helmet_precision_not_collapsed"]["pass"] is False


def test_gate_fails_on_material_person_helmet_vest_regression():
    import promote_vision_v1_2 as p

    report = _fake_report(v11_no_helmet_recall=0.175, v12_no_helmet_recall=0.45, v11_no_helmet_precision=0.4, v12_no_helmet_precision=0.4, regress=True)
    gate = p.evaluate_gate(report)
    assert gate["overall_pass"] is False
    assert gate["checks"]["no_material_person_helmet_vest_regression"]["pass"] is False


# ---------------------------------------------------------------------------
# promote_vision_v1_2: promote() side effects (registry write / artifact copy)
# and refusal paths
# ---------------------------------------------------------------------------


def test_promote_writes_new_artifact_and_registry_without_touching_v1_1(tmp_path, monkeypatch):
    import promote_vision_v1_2 as p

    artifacts_dir = tmp_path / "models" / "artifacts"
    artifacts_dir.mkdir(parents=True)
    eval_dir = tmp_path / "models" / "evaluation"
    eval_dir.mkdir(parents=True)

    v11_artifact = artifacts_dir / "ppe-yolo11n.pt"
    v11_artifact.write_bytes(b"v1.1 bytes -- must never change")
    v11_digest_before = hashlib.sha256(v11_artifact.read_bytes()).hexdigest()

    candidate = artifacts_dir / "ppe-yolo11n-v1.2-epoch7-candidate.pt"
    candidate.write_bytes(b"v1.2 candidate bytes")

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"ppe_detector": {
        "version": "1.1", "artifact_path": "models/artifacts/ppe-yolo11n.pt",
        "sha256": v11_digest_before, "artifact_size_bytes": v11_artifact.stat().st_size,
    }}))

    # Full isolation: promote() on a passing gate also touches
    # CANDIDATE_THRESHOLDS_PATH/ACTIVE_THRESHOLDS_PATH -- an earlier version of
    # this test monkeypatched only REPO_ROOT/ARTIFACTS_DIR/REGISTRY_PATH and, as
    # a result, actually overwrote the real backend/app/inference/ppe_thresholds.json
    # with whatever real models/evaluation/vision_v1.2_candidate_thresholds.json
    # happened to exist on disk -- found live when it silently switched the
    # active runtime thresholds to a rejected v1.2 candidate's values. Every
    # path promote() can write to must be monkeypatched here.
    real_active_thresholds_path = p.ACTIVE_THRESHOLDS_PATH
    real_active_thresholds_before = real_active_thresholds_path.read_text()

    fake_candidate_thresholds_path = tmp_path / "vision_v1.2_candidate_thresholds.json"
    fake_candidate_thresholds_path.write_text(json.dumps({"version": "1.2-candidate", "thresholds": {"person": 0.11}}))
    fake_active_thresholds_path = tmp_path / "ppe_thresholds.json"
    fake_active_thresholds_path.write_text(json.dumps({"version": "1.0", "thresholds": {"person": 0.4}}))

    monkeypatch.setattr(p, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(p, "ARTIFACTS_DIR", artifacts_dir)
    monkeypatch.setattr(p, "REGISTRY_PATH", registry_path)
    monkeypatch.setattr(p, "CANDIDATE_THRESHOLDS_PATH", fake_candidate_thresholds_path)
    monkeypatch.setattr(p, "ACTIVE_THRESHOLDS_PATH", fake_active_thresholds_path)

    gate_result = {"overall_pass": True, "checks": {}}
    result = p.promote(candidate, gate_result, report={})

    assert result["promoted"] is True
    assert result["thresholds_switched"] is True
    new_artifact = artifacts_dir / "ppe-yolo11n-v1.2.pt"
    assert new_artifact.exists()
    assert hashlib.sha256(new_artifact.read_bytes()).hexdigest() == result["sha256"]

    # v1.1's artifact bytes must be completely untouched.
    assert hashlib.sha256(v11_artifact.read_bytes()).hexdigest() == v11_digest_before

    registry = json.loads(registry_path.read_text())
    assert registry["ppe_detector"]["version"] == "1.2"
    assert registry["ppe_detector"]["artifact_path"] == "models/artifacts/ppe-yolo11n-v1.2.pt"
    assert registry["ppe_detector"]["sha256"] == result["sha256"]
    assert registry["ppe_detector"]["previous_version"]["version"] == "1.1"
    assert registry["ppe_detector"]["previous_version"]["sha256"] == v11_digest_before

    # The fake active-thresholds file DID get switched (that's the feature under test)...
    assert json.loads(fake_active_thresholds_path.read_text())["version"] == "1.2-candidate"
    # ...but the REAL production thresholds file was never touched by this test.
    assert real_active_thresholds_path.read_text() == real_active_thresholds_before


def test_promote_refuses_missing_candidate_artifact(tmp_path, monkeypatch):
    import promote_vision_v1_2 as p

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"ppe_detector": {"version": "1.1", "sha256": "a" * 64}}))

    monkeypatch.setattr(p, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(p, "ARTIFACTS_DIR", artifacts_dir)
    monkeypatch.setattr(p, "REGISTRY_PATH", registry_path)

    missing_candidate = artifacts_dir / "ppe-yolo11n-v1.2-epoch7-candidate.pt"
    registry_before = registry_path.read_text()

    with pytest.raises(FileNotFoundError):
        p.promote(missing_candidate, {"overall_pass": True}, report={})

    # Registry must be completely untouched on this refusal path.
    assert registry_path.read_text() == registry_before
