"""Phase 3: validated-threshold loading with a safe fallback to spec defaults."""

import json

from app.inference.vision_worker_impl import _SPEC_DEFAULT_THRESHOLDS, _load_class_conf_thresholds


def test_loads_real_frozen_thresholds_file():
    thresholds = _load_class_conf_thresholds()
    assert set(thresholds) == {"person", "helmet", "vest", "no_helmet"}
    assert all(0.0 <= v <= 1.0 for v in thresholds.values())


def test_falls_back_to_spec_defaults_when_file_missing(tmp_path, monkeypatch):
    import app.inference.vision_worker_impl as m

    monkeypatch.setattr(m, "_THRESHOLDS_PATH", tmp_path / "does-not-exist.json")
    assert m._load_class_conf_thresholds() == _SPEC_DEFAULT_THRESHOLDS


def test_falls_back_to_spec_defaults_when_file_malformed(tmp_path, monkeypatch):
    import app.inference.vision_worker_impl as m

    bad = tmp_path / "ppe_thresholds.json"
    bad.write_text("{not valid json")
    monkeypatch.setattr(m, "_THRESHOLDS_PATH", bad)
    assert m._load_class_conf_thresholds() == _SPEC_DEFAULT_THRESHOLDS


def test_falls_back_when_class_set_does_not_match(tmp_path, monkeypatch):
    import app.inference.vision_worker_impl as m

    wrong = tmp_path / "ppe_thresholds.json"
    wrong.write_text(json.dumps({"thresholds": {"person": 0.3, "helmet": 0.3}}))
    monkeypatch.setattr(m, "_THRESHOLDS_PATH", wrong)
    assert m._load_class_conf_thresholds() == _SPEC_DEFAULT_THRESHOLDS
