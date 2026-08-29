"""Runtime adapter for the physics-informed residual GRU (Phase 4).

Mirrors app/inference/leak_model.py's fallback-first design: the physics
forecast is ALWAYS computed and ALWAYS usable on its own (forecast_service.py
never blocks on this adapter). This adapter only ever ADDS an optional
residual correction on top.

Falls back to physics-only (status DEGRADED, never a crash) when the artifact
is: absent, corrupt, incompatible, times out, returns non-finite values,
produces the wrong output shape, or was trained with a different feature
schema than this runtime expects.
"""

import hashlib
import json
import time
from dataclasses import dataclass

import numpy as np

from app.contracts.enums import ModelStatus
from app.inference.gru_dataset import FEATURE_NAMES, INPUT_STEPS, OUTPUT_STEPS
from app.logging_config import get_logger
from app.settings import get_settings

logger = get_logger(__name__)

INFERENCE_TIMEOUT_SECONDS = 2.0


@dataclass
class GruForecastResult:
    residuals: list[float] | None  # length OUTPUT_STEPS, ppm
    lower_bounds: list[float] | None
    upper_bounds: list[float] | None
    status: ModelStatus
    model_version: str | None
    reason: str | None = None


class ForecastGruAdapter:
    def __init__(self) -> None:
        self._model = None
        self._scaler_mean: np.ndarray | None = None
        self._scaler_std: np.ndarray | None = None
        self._q05: np.ndarray | None = None
        self._q95: np.ndarray | None = None
        self._version: str | None = None
        self._status = ModelStatus.UNAVAILABLE
        self._load()

    @property
    def status(self) -> ModelStatus:
        return self._status

    def _load(self) -> None:
        settings = get_settings()
        registry_path = settings.model_registry_path
        if not registry_path.exists():
            logger.warning("model registry missing; GRU forecast falls back to physics-only")
            return
        try:
            registry = json.loads(registry_path.read_text())
            entry = registry.get("forecast_gru")
            if entry is None:
                return

            repo_root = settings.models_dir.parent
            weights_path = repo_root / entry["artifact_path"]
            scaler_path = repo_root / entry["scaler_path"]
            schema_path = repo_root / entry["feature_schema_path"]

            if not weights_path.exists() or not scaler_path.exists() or not schema_path.exists():
                logger.warning("GRU artifact/scaler/schema file missing; falling back to physics-only")
                return

            digest = hashlib.sha256(weights_path.read_bytes()).hexdigest()
            if digest != entry.get("sha256"):
                logger.error("GRU weights checksum mismatch; falling back to physics-only")
                return

            schema = json.loads(schema_path.read_text())
            if schema.get("feature_names") != FEATURE_NAMES or schema.get("input_steps") != INPUT_STEPS or schema.get("output_steps") != OUTPUT_STEPS:
                logger.error("GRU feature schema mismatch; falling back to physics-only")
                return

            scaler = json.loads(scaler_path.read_text())
            self._scaler_mean = np.array(scaler["feature_mean"], dtype=np.float32)
            self._scaler_std = np.array(scaler["feature_std"], dtype=np.float32)
            self._q05 = np.array(schema["residual_bounds_q05"], dtype=np.float32)
            self._q95 = np.array(schema["residual_bounds_q95"], dtype=np.float32)

            import torch

            from app.inference.gru_model import ResidualGRU

            model = ResidualGRU()
            state_dict = torch.load(weights_path, map_location="cpu", weights_only=True)
            model.load_state_dict(state_dict)
            model.eval()
            self._model = model
            self._version = entry.get("version")
            self._status = ModelStatus.OK
        except Exception:
            logger.exception("failed to load GRU forecast model; falling back to physics-only")
            self._model = None
            self._status = ModelStatus.UNAVAILABLE

    def predict(self, feature_window: np.ndarray) -> GruForecastResult:
        """feature_window: (INPUT_STEPS, len(FEATURE_NAMES)) raw (pre-scaled per
        gru_dataset's fixed light scale, NOT yet standardized -- this method
        applies the train-fit standardization itself)."""
        if self._model is None:
            return GruForecastResult(None, None, None, ModelStatus.FALLBACK, None, reason="model_unavailable")

        if feature_window.shape != (INPUT_STEPS, len(FEATURE_NAMES)):
            logger.error("GRU input shape mismatch; falling back to physics-only", extra={"extra_fields": {"shape": str(feature_window.shape)}})
            return GruForecastResult(None, None, None, ModelStatus.FALLBACK, self._version, reason="invalid_input_shape")

        try:
            import torch

            t0 = time.monotonic()
            normalized = (feature_window - self._scaler_mean) / self._scaler_std
            with torch.no_grad():
                x = torch.from_numpy(normalized.astype(np.float32)).unsqueeze(0)
                pred = self._model(x).squeeze(0).numpy()
            elapsed = time.monotonic() - t0
            if elapsed > INFERENCE_TIMEOUT_SECONDS:
                logger.error("GRU inference exceeded timeout; falling back to physics-only", extra={"extra_fields": {"elapsed_s": elapsed}})
                return GruForecastResult(None, None, None, ModelStatus.FALLBACK, self._version, reason="inference_timeout")

            if pred.shape != (OUTPUT_STEPS,) or not np.all(np.isfinite(pred)):
                logger.error("GRU produced non-finite or wrong-shape output; falling back to physics-only")
                return GruForecastResult(None, None, None, ModelStatus.FALLBACK, self._version, reason="invalid_output")

            lower = (pred + self._q05).tolist()
            upper = (pred + self._q95).tolist()
            return GruForecastResult(pred.tolist(), lower, upper, ModelStatus.OK, self._version)
        except Exception:
            logger.exception("GRU inference failed; falling back to physics-only")
            return GruForecastResult(None, None, None, ModelStatus.FALLBACK, self._version, reason="inference_exception")


_adapter: ForecastGruAdapter | None = None


def get_forecast_gru() -> ForecastGruAdapter:
    global _adapter
    if _adapter is None:
        _adapter = ForecastGruAdapter()
    return _adapter


def reset_forecast_gru_for_tests() -> None:
    global _adapter
    _adapter = None
