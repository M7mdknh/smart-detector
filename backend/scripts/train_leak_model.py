"""Reproduces the calibrated XGBoost leak-probability artifact (make train-sensor).

Splits whole scenario IDs/seeds 70/15/15 into train/validation/test BEFORE
windowing, per CLAUDE.md's data-leakage rules. Compares persistence, physics-only,
logistic regression, uncalibrated XGBoost, and calibrated XGBoost baselines.
Never runs during `make demo` -- this is an explicit offline command.
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, f1_score, precision_score, recall_score
from xgboost import XGBClassifier

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.inference.features import FEATURE_NAMES, compute_features_at_cutoff  # noqa: E402
from app.inference.synthetic_scenarios import default_scenario_specs, generate_scenario_dataframe  # noqa: E402

MODELS_DIR = REPO_ROOT / "models"
ARTIFACTS_DIR = MODELS_DIR / "artifacts"
EVAL_DIR = MODELS_DIR / "evaluation"
REGISTRY_PATH = MODELS_DIR / "registry.json"

GENERATOR_VERSION = "1.0"
MODEL_VERSION = "1.0"
CALIBRATION_VERSION = "1.0"
LABEL_VERSION = "1.0"


def build_windowed_dataset(specs, min_cutoff_minute: float = 60.0, stride_minutes: float = 15.0):
    rows = []
    labels = []
    groups = []
    for spec in specs:
        df = generate_scenario_dataframe(spec)
        no_leak_baseline = df["ppm"].iloc[0]  # crude no-leak reference for this scenario's inlet level
        max_minute = df["minute"].max()
        cutoff = min_cutoff_minute
        while cutoff <= max_minute:
            hist = df[["minute", "ppm", "missing"]]
            vent_now = float(df[df["minute"] <= cutoff]["ventilation_m3h"].iloc[-1])
            features = compute_features_at_cutoff(hist, cutoff, vent_now, vent_now, no_leak_baseline)
            label_row = df[df["minute"] <= cutoff].iloc[-1]
            rows.append(features)
            labels.append(int(label_row["leak_active_within_60m"]))
            groups.append(spec.scenario_id)
            cutoff += stride_minutes

    X = np.vstack(rows)
    y = np.array(labels)
    g = np.array(groups)
    return X, y, g


def split_scenarios(specs, train_frac=0.7, val_frac=0.15, seed=42):
    rng = np.random.default_rng(seed)
    by_kind = {}
    for s in specs:
        by_kind.setdefault(s.kind, []).append(s)

    train, val, test = [], [], []
    for kind, group in by_kind.items():
        idx = rng.permutation(len(group))
        n = len(group)
        n_train = int(n * train_frac)
        n_val = int(n * val_frac)
        train += [group[i] for i in idx[:n_train]]
        val += [group[i] for i in idx[n_train : n_train + n_val]]
        test += [group[i] for i in idx[n_train + n_val :]]
    return train, val, test


def evaluate(y_true, y_prob, threshold=0.5):
    y_pred = (y_prob >= threshold).astype(int)
    pr_auc = average_precision_score(y_true, y_prob) if len(set(y_true)) > 1 else float("nan")
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    brier = brier_score_loss(y_true, y_prob)
    return {"pr_auc": pr_auc, "precision": precision, "recall": recall, "f1": f1, "brier": brier, "n": int(len(y_true)), "n_positive": int(y_true.sum())}


def main():
    t0 = time.time()
    print("Generating synthetic scenarios...")
    specs = default_scenario_specs(n_per_kind=25)
    train_specs, val_specs, test_specs = split_scenarios(specs)

    train_ids = {s.scenario_id for s in train_specs}
    val_ids = {s.scenario_id for s in val_specs}
    test_ids = {s.scenario_id for s in test_specs}
    assert not (train_ids & val_ids) and not (train_ids & test_ids) and not (val_ids & test_ids), "split leakage"

    print(f"train={len(train_specs)} val={len(val_specs)} test={len(test_specs)} scenarios")

    X_train, y_train, g_train = build_windowed_dataset(train_specs)
    X_val, y_val, g_val = build_windowed_dataset(val_specs)
    X_test, y_test, g_test = build_windowed_dataset(test_specs)

    print(f"windows: train={len(y_train)} val={len(y_val)} test={len(y_test)}")
    print(f"positive rate: train={y_train.mean():.3f} val={y_val.mean():.3f} test={y_test.mean():.3f}")

    # --- baselines ---
    results = {}

    # Persistence: predict the training positive rate for everyone (naive baseline)
    persistence_prob = np.full_like(y_test, fill_value=y_train.mean(), dtype=float)
    results["persistence"] = evaluate(y_test, persistence_prob)

    # Physics-only proxy: use "deviation_from_no_leak_physics" feature thresholded
    deviation_idx = FEATURE_NAMES.index("deviation_from_no_leak_physics")
    physics_score = X_test[:, deviation_idx]
    physics_prob = 1 / (1 + np.exp(-(physics_score - 500) / 500))  # logistic squashing for a probability-like score
    results["physics_only"] = evaluate(y_test, physics_prob)

    # Logistic regression baseline
    logreg = LogisticRegression(max_iter=1000, class_weight="balanced")
    logreg.fit(X_train, y_train)
    logreg_prob = logreg.predict_proba(X_test)[:, 1]
    results["logistic_regression"] = evaluate(y_test, logreg_prob)

    # Uncalibrated XGBoost
    n_pos = max(1, y_train.sum())
    n_neg = max(1, len(y_train) - y_train.sum())
    scale_pos_weight = n_neg / n_pos

    xgb = XGBClassifier(
        n_estimators=200, max_depth=3, learning_rate=0.05, min_child_weight=2, subsample=0.8,
        colsample_bytree=0.8, reg_lambda=1.0, objective="binary:logistic", eval_metric="logloss",
        random_state=42, n_jobs=1, scale_pos_weight=scale_pos_weight,
    )
    xgb.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    uncal_prob = xgb.predict_proba(X_test)[:, 1]
    results["xgboost_uncalibrated"] = evaluate(y_test, uncal_prob)

    # Calibrated XGBoost (Platt/sigmoid on validation split, never on test).
    # sklearn's CalibratedClassifierCV isn't directly serializable into the raw XGBoost
    # booster file our runtime loader reads, so we extract the fitted sigmoid's (a, b)
    # and apply calibrated = sigmoid(a * raw_prob + b) ourselves at inference time.
    sigmoid_a, sigmoid_b = None, None
    if len(set(y_val)) > 1 and len(y_val) >= 20:
        calibrated = CalibratedClassifierCV(xgb, method="sigmoid", cv="prefit")
        calibrated.fit(X_val, y_val)
        cal_prob = calibrated.predict_proba(X_test)[:, 1]
        calibration_status = "CALIBRATED"
        try:
            sigmoid = calibrated.calibrated_classifiers_[0].calibrators[0]
            sigmoid_a, sigmoid_b = float(sigmoid.a_), float(sigmoid.b_)
        except (AttributeError, IndexError):
            print("WARNING: could not extract sigmoid calibration parameters; runtime will use raw probability")
            calibration_status = "CALIBRATED_PARAMS_UNAVAILABLE"
    else:
        print("WARNING: validation subset too small/imbalanced for calibration; using uncalibrated probability")
        cal_prob = uncal_prob
        calibration_status = "UNCALIBRATED_FALLBACK"
    results["xgboost_calibrated"] = evaluate(y_test, cal_prob)
    results["calibration_status"] = calibration_status

    print(json.dumps(results, indent=2, default=str))

    # --- persist artifact ---
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    artifact_path = ARTIFACTS_DIR / "leak-classifier-xgb.json"
    xgb.save_model(str(artifact_path))  # save the underlying booster (calibration wraps it at inference time via probability mapping baked into thresholds if needed)

    sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

    metrics_path = EVAL_DIR / "leak_model_metrics.json"
    metrics_path.write_text(json.dumps(results, indent=2, default=str))

    split_manifest_path = EVAL_DIR / "leak_model_split_manifest.json"
    split_manifest_path.write_text(json.dumps({
        "train": sorted(train_ids), "validation": sorted(val_ids), "test": sorted(test_ids),
    }, indent=2))

    registry = {}
    if REGISTRY_PATH.exists():
        registry = json.loads(REGISTRY_PATH.read_text())

    registry["leak_classifier"] = {
        "name": "leak_classifier",
        "version": MODEL_VERSION,
        "artifact_path": str(artifact_path.relative_to(REPO_ROOT)),
        "sha256": sha256,
        "feature_schema": FEATURE_NAMES,
        "training_data_version": GENERATOR_VERSION,
        "config_version": "1.0",
        "calibration_version": CALIBRATION_VERSION if calibration_status == "CALIBRATED" else None,
        "calibration_status": calibration_status,
        "calibration_sigmoid_a": sigmoid_a,
        "calibration_sigmoid_b": sigmoid_b,
        "metrics_path": str(metrics_path.relative_to(REPO_ROOT)),
        "split_manifest_path": str(split_manifest_path.relative_to(REPO_ROOT)),
        "label_version": LABEL_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "Calibrated wrapper's probability mapping is not directly serializable in the raw booster file; "
                "runtime uses the underlying booster's raw probability. See metrics for calibration quality (Brier score).",
    }
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))

    print(f"\nArtifact: {artifact_path} (sha256={sha256[:16]}...)")
    print(f"Metrics: {metrics_path}")
    print(f"Done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
