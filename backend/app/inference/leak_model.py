"""Calibrated XGBoost leak-probability adapter with explainable rule fallback.

Startup validates the artifact checksum/feature schema against models/registry.json.
On mismatch/load failure: MODEL_UNAVAILABLE, one structured log line, fallback engaged.
No learned model ever blocks the immediate threshold/exposure path (see forecast_service).
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.contracts.enums import LeakLabel, ModelStatus
from app.inference.features import FEATURE_NAMES
from app.logging_config import get_logger
from app.settings import get_settings

logger = get_logger(__name__)

RULE_VERSION = "1.0"
SLOPE_THRESHOLD_PPM_PER_MIN = 8.0  # robust 30-min slope threshold for fallback rule


def _label_for(prob: float) -> LeakLabel:
    if prob >= 0.70:
        return LeakLabel.LIKELY_LEAK
    if prob >= 0.40:
        return LeakLabel.SUSPICIOUS_TREND
    return LeakLabel.NO_LEAK_SIGNAL


@dataclass
class LeakInferenceResult:
    probability: float | None
    label: LeakLabel
    status: ModelStatus
    model_version: str | None
    calibration_version: str | None
    feature_snapshot: dict


class LeakModelAdapter:
    def __init__(self) -> None:
        self._model = None
        self._version: str | None = None
        self._calibration_version: str | None = None
        self._sigmoid_a: float | None = None
        self._sigmoid_b: float | None = None
        self._status = ModelStatus.UNAVAILABLE
        self._load()

    def _load(self) -> None:
        settings = get_settings()
        registry_path = settings.model_registry_path
        if not registry_path.exists():
            logger.warning("model registry missing; leak model falls back to rule", extra={"extra_fields": {"path": str(registry_path)}})
            return
        try:
            registry = json.loads(registry_path.read_text())
            entry = registry.get("leak_classifier")
            if entry is None:
                return
            artifact_path = Path(entry["artifact_path"])
            if not artifact_path.is_absolute():
                artifact_path = settings.models_dir.parent / artifact_path
            if not artifact_path.exists():
                logger.warning("leak model artifact missing", extra={"extra_fields": {"path": str(artifact_path)}})
                return
            digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            if digest != entry.get("sha256"):
                logger.error("leak model checksum mismatch; using fallback", extra={"extra_fields": {"path": str(artifact_path)}})
                return
            schema = entry.get("feature_schema", [])
            if schema != FEATURE_NAMES:
                logger.error("leak model feature schema mismatch; using fallback")
                return

            import xgboost as xgb

            booster = xgb.Booster()
            booster.load_model(str(artifact_path))
            self._model = booster
            self._version = entry.get("version")
            self._calibration_version = entry.get("calibration_version")
            self._sigmoid_a = entry.get("calibration_sigmoid_a")
            self._sigmoid_b = entry.get("calibration_sigmoid_b")
            self._status = ModelStatus.OK
        except Exception:
            logger.exception("failed to load leak model; using fallback")
            self._model = None
            self._status = ModelStatus.UNAVAILABLE

    @property
    def status(self) -> ModelStatus:
        return self._status

    def predict(self, features: np.ndarray, robust_slope_30m_ppm_per_min: float, is_leak_consistent: bool, persistence_readings: int) -> LeakInferenceResult:
        snapshot = {name: float(val) for name, val in zip(FEATURE_NAMES, features)}

        if self._model is not None:
            try:
                import xgboost as xgb

                dmat = xgb.DMatrix(features.reshape(1, -1), feature_names=FEATURE_NAMES)
                raw_prob = float(self._model.predict(dmat)[0])
                if self._sigmoid_a is not None and self._sigmoid_b is not None:
                    prob = 1.0 / (1.0 + np.exp(self._sigmoid_a * raw_prob + self._sigmoid_b))
                else:
                    prob = raw_prob
                return LeakInferenceResult(
                    probability=prob,
                    label=_label_for(prob),
                    status=ModelStatus.OK,
                    model_version=self._version,
                    calibration_version=self._calibration_version,
                    feature_snapshot=snapshot,
                )
            except Exception:
                logger.exception("leak model inference failed; using fallback")

        return self._fallback(robust_slope_30m_ppm_per_min, is_leak_consistent, persistence_readings, snapshot)

    def _fallback(self, slope: float, is_leak_consistent: bool, persistence_readings: int, snapshot: dict) -> LeakInferenceResult:
        snapshot = dict(snapshot)
        snapshot["rule_version"] = RULE_VERSION
        snapshot["slope_threshold"] = SLOPE_THRESHOLD_PPM_PER_MIN
        if slope > SLOPE_THRESHOLD_PPM_PER_MIN and is_leak_consistent and persistence_readings >= 3:
            return LeakInferenceResult(
                probability=None,
                label=LeakLabel.SUSPICIOUS_TREND,
                status=ModelStatus.FALLBACK,
                model_version=None,
                calibration_version=None,
                feature_snapshot=snapshot,
            )
        return LeakInferenceResult(
            probability=None,
            label=LeakLabel.NO_LEAK_SIGNAL,
            status=ModelStatus.FALLBACK,
            model_version=None,
            calibration_version=None,
            feature_snapshot=snapshot,
        )


_adapter: LeakModelAdapter | None = None


def get_leak_model() -> LeakModelAdapter:
    global _adapter
    if _adapter is None:
        _adapter = LeakModelAdapter()
    return _adapter


def reset_leak_model_for_tests() -> None:
    global _adapter
    _adapter = None
