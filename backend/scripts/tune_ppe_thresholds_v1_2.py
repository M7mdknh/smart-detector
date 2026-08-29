"""Validation-only confidence-threshold tuning for the v1.2 PPE-detector
CANDIDATE (external-data/converted_dataset, canonical 4-class ids 0-3),
mirroring the exact methodology of scripts/tune_ppe_thresholds.py used for
the active v1.1 artifact (models/evaluation/ppe_threshold_sweep.json /
app/inference/ppe_thresholds.json).

Unlike v1.1's sweep (which runs against the 11-class construction-ppe.yaml),
this sweeps against external-data/converted_dataset/data.yaml's VALIDATION
split only -- the v1.2 candidate's own data.yaml, which already uses the
canonical class ids [person=0, helmet=1, vest=2, no_helmet=3], so
`model.val()` can be called directly (no cross-dataset class-id mismatch,
unlike the test-split comparative evaluation).

Test data is never touched here. Output is a CANDIDATE thresholds file
(models/evaluation/vision_v1.2_candidate_thresholds.json) -- it does NOT
overwrite app/inference/ppe_thresholds.json (the active v1.1 runtime
thresholds), and is only wired into app/inference/ppe_thresholds.json if/when
the promotion gate passes and v1.2 is promoted.
"""

import json
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

MODELS_DIR = REPO_ROOT / "models"
EVAL_DIR = MODELS_DIR / "evaluation"
DATA_YAML = str(REPO_ROOT / "external-data" / "converted_dataset" / "data.yaml")

RUNTIME_DATASET_IDS = {"person": 0, "helmet": 1, "vest": 2, "no_helmet": 3}
CANDIDATE_THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
PRECISION_FLOOR = {"person": 0.60, "helmet": 0.70, "vest": 0.60, "no_helmet": 0.15}


def sweep(artifact_path: Path):
    from ultralytics import YOLO

    model = YOLO(str(artifact_path))
    sweep_results: dict[str, list[dict]] = {name: [] for name in RUNTIME_DATASET_IDS}

    for conf in CANDIDATE_THRESHOLDS:
        metrics = model.val(data=DATA_YAML, split="val", conf=conf, device="0", verbose=False)
        for name, dataset_id in RUNTIME_DATASET_IDS.items():
            try:
                idx = list(metrics.box.ap_class_index).index(dataset_id)
                p, r = float(metrics.box.p[idx]), float(metrics.box.r[idx])
            except ValueError:
                p, r = 0.0, 0.0
            f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
            sweep_results[name].append({"conf": conf, "precision": p, "recall": r, "f1": f1})

    return sweep_results


def select_thresholds(sweep_results: dict[str, list[dict]]) -> dict[str, dict]:
    chosen = {}
    for name, points in sweep_results.items():
        floor = PRECISION_FLOOR[name]
        eligible = [pt for pt in points if pt["precision"] >= floor]
        if name == "no_helmet":
            pool = eligible or points
            best = min(pool, key=lambda pt: pt["conf"])
        else:
            pool = eligible or points
            best = max(pool, key=lambda pt: pt["f1"])
        chosen[name] = best
    return chosen


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=str, required=True)
    parser.add_argument("--out", type=str, default=str(EVAL_DIR / "vision_v1.2_candidate_thresholds.json"))
    args = parser.parse_args()

    artifact_path = Path(args.artifact)
    print(f"Sweeping candidate confidence thresholds on the VALIDATION split (never test) for {artifact_path}...")
    sweep_results = sweep(artifact_path)
    print(json.dumps(sweep_results, indent=2))

    chosen = select_thresholds(sweep_results)
    print("\nSelected thresholds (validation-derived, v1.2 candidate):")
    print(json.dumps(chosen, indent=2))

    config = {
        "version": "1.2-candidate",
        "artifact": str(artifact_path),
        "derived_from_split": "val",
        "derived_from_dataset": "external-data/converted_dataset (Industrial-Safety, Roboflow, MIT license)",
        "candidate_thresholds_swept": CANDIDATE_THRESHOLDS,
        "precision_floor": PRECISION_FLOOR,
        "thresholds": {name: pt["conf"] for name, pt in chosen.items()},
        "selection_validation_metrics": chosen,
        "nms_iou": 0.5,
        "methodology": "Identical methodology to scripts/tune_ppe_thresholds.py (v1.1): global-confidence sweep through Ultralytics model.val() on the validation split at each candidate threshold. no_helmet optimizes recall subject to a precision floor; other classes maximize F1.",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(config, indent=2))
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
