"""Phase 4/10: GRU adapter safe-fallback regression tests. Every listed failure
mode (absent/corrupt/incompatible/timeout/non-finite/wrong-shape/schema-mismatch)
must degrade to physics-only, never crash or block ingestion."""

import json

import numpy as np
import pytest

from app.contracts.enums import ModelStatus
from app.inference.forecast_gru import ForecastGruAdapter
from app.inference.gru_dataset import FEATURE_NAMES, INPUT_STEPS, OUTPUT_STEPS


@pytest.fixture
def real_registry_path():
    from app.settings import get_settings

    return get_settings().model_registry_path


def test_real_artifact_loads_and_predicts(real_registry_path):
    if not real_registry_path.exists():
        pytest.skip("no registry present in this environment")
    adapter = ForecastGruAdapter()
    if adapter.status != ModelStatus.OK:
        pytest.skip("GRU artifact not registered in this environment")
    window = np.random.default_rng(0).normal(0, 0.1, size=(INPUT_STEPS, len(FEATURE_NAMES)))
    result = adapter.predict(window)
    assert result.status == ModelStatus.OK
    assert len(result.residuals) == OUTPUT_STEPS
    assert all(np.isfinite(v) for v in result.residuals)


def test_missing_registry_falls_back(tmp_path, monkeypatch):
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.get_settings(), "model_registry_path", tmp_path / "nope.json")
    adapter = ForecastGruAdapter()
    assert adapter.status == ModelStatus.UNAVAILABLE


def test_registry_without_forecast_gru_entry_falls_back(tmp_path, monkeypatch):
    from app import settings as settings_module

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"leak_classifier": {}}))
    monkeypatch.setattr(settings_module.get_settings(), "model_registry_path", registry_path)
    adapter = ForecastGruAdapter()
    assert adapter.status == ModelStatus.UNAVAILABLE


def test_missing_artifact_file_falls_back(tmp_path, monkeypatch):
    from app import settings as settings_module

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({
        "forecast_gru": {
            "artifact_path": "models/artifacts/does-not-exist.pt",
            "scaler_path": "models/artifacts/does-not-exist-scaler.json",
            "feature_schema_path": "models/artifacts/does-not-exist-schema.json",
            "sha256": "0" * 64, "version": "1.0",
        }
    }))
    monkeypatch.setattr(settings_module.get_settings(), "model_registry_path", registry_path)
    adapter = ForecastGruAdapter()
    assert adapter.status == ModelStatus.UNAVAILABLE


def test_checksum_mismatch_falls_back(tmp_path, monkeypatch):
    from app import settings as settings_module

    artifacts_dir = tmp_path / "models" / "artifacts"
    artifacts_dir.mkdir(parents=True)
    weights_path = artifacts_dir / "forecast-gru.pt"
    weights_path.write_bytes(b"not a real checkpoint")
    scaler_path = artifacts_dir / "scaler.json"
    scaler_path.write_text(json.dumps({"feature_mean": [0] * 7, "feature_std": [1] * 7}))
    schema_path = artifacts_dir / "schema.json"
    schema_path.write_text(json.dumps({
        "feature_names": FEATURE_NAMES, "input_steps": INPUT_STEPS, "output_steps": OUTPUT_STEPS,
        "residual_bounds_q05": [0] * OUTPUT_STEPS, "residual_bounds_q95": [0] * OUTPUT_STEPS,
    }))
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({
        "forecast_gru": {
            "artifact_path": f"models/artifacts/{weights_path.name}",
            "scaler_path": f"models/artifacts/{scaler_path.name}",
            "feature_schema_path": f"models/artifacts/{schema_path.name}",
            "sha256": "wrong-checksum", "version": "1.0",
        }
    }))
    settings = settings_module.get_settings()
    monkeypatch.setattr(settings, "model_registry_path", registry_path)
    monkeypatch.setattr(settings, "models_dir", tmp_path / "models")
    adapter = ForecastGruAdapter()
    assert adapter.status == ModelStatus.UNAVAILABLE


def test_schema_mismatch_falls_back(tmp_path, monkeypatch):
    import hashlib

    from app import settings as settings_module

    artifacts_dir = tmp_path / "models" / "artifacts"
    artifacts_dir.mkdir(parents=True)
    weights_path = artifacts_dir / "forecast-gru.pt"
    weights_path.write_bytes(b"not a real checkpoint")
    scaler_path = artifacts_dir / "scaler.json"
    scaler_path.write_text(json.dumps({"feature_mean": [0] * 7, "feature_std": [1] * 7}))
    schema_path = artifacts_dir / "schema.json"
    schema_path.write_text(json.dumps({
        "feature_names": ["wrong", "schema"], "input_steps": 999, "output_steps": 1,
        "residual_bounds_q05": [0], "residual_bounds_q95": [0],
    }))
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({
        "forecast_gru": {
            "artifact_path": f"models/artifacts/{weights_path.name}",
            "scaler_path": f"models/artifacts/{scaler_path.name}",
            "feature_schema_path": f"models/artifacts/{schema_path.name}",
            "sha256": hashlib.sha256(weights_path.read_bytes()).hexdigest(), "version": "1.0",
        }
    }))
    settings = settings_module.get_settings()
    monkeypatch.setattr(settings, "model_registry_path", registry_path)
    monkeypatch.setattr(settings, "models_dir", tmp_path / "models")
    adapter = ForecastGruAdapter()
    assert adapter.status == ModelStatus.UNAVAILABLE


def test_predict_with_no_model_returns_fallback_without_crashing():
    adapter = ForecastGruAdapter.__new__(ForecastGruAdapter)
    adapter._model = None
    result = adapter.predict(np.zeros((INPUT_STEPS, len(FEATURE_NAMES))))
    assert result.status == ModelStatus.FALLBACK
    assert result.residuals is None


def test_predict_with_wrong_input_shape_falls_back():
    adapter = ForecastGruAdapter.__new__(ForecastGruAdapter)
    adapter._model = object()  # any non-None sentinel; shape check happens before model use
    adapter._version = "1.0"
    result = adapter.predict(np.zeros((5, 3)))
    assert result.status == ModelStatus.FALLBACK
    assert result.reason == "invalid_input_shape"


def test_predict_with_non_finite_model_output_falls_back(monkeypatch):
    class _NaNModel:
        def __call__(self, x):
            import torch

            return torch.full((1, OUTPUT_STEPS), float("nan"))

        def eval(self):
            pass

    adapter = ForecastGruAdapter.__new__(ForecastGruAdapter)
    adapter._model = _NaNModel()
    adapter._version = "1.0"
    adapter._scaler_mean = np.zeros(len(FEATURE_NAMES), dtype=np.float32)
    adapter._scaler_std = np.ones(len(FEATURE_NAMES), dtype=np.float32)
    result = adapter.predict(np.zeros((INPUT_STEPS, len(FEATURE_NAMES))))
    assert result.status == ModelStatus.FALLBACK
    assert result.reason == "invalid_output"


def test_predict_exception_falls_back_gracefully():
    class _BrokenModel:
        def __call__(self, x):
            raise RuntimeError("simulated inference crash")

    adapter = ForecastGruAdapter.__new__(ForecastGruAdapter)
    adapter._model = _BrokenModel()
    adapter._version = "1.0"
    adapter._scaler_mean = np.zeros(len(FEATURE_NAMES), dtype=np.float32)
    adapter._scaler_std = np.ones(len(FEATURE_NAMES), dtype=np.float32)
    result = adapter.predict(np.zeros((INPUT_STEPS, len(FEATURE_NAMES))))
    assert result.status == ModelStatus.FALLBACK
    assert result.reason == "inference_exception"
