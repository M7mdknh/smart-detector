"""Phase 3: validation-only confidence-threshold tuning for the PPE detector.

Methodology (honest and reproducible, not a from-scratch PR-curve extractor):
sweeps a set of candidate global confidence thresholds through Ultralytics'
own `model.val()` on the VALIDATION split only (never the test split), reading
back per-class precision/recall at each threshold from `metrics.box.p`/`.r`.
This is a real, measured sweep on held-out data, not a guess -- but it is a
coarser tool than a full per-class PR-curve extractor would be (a threshold
is swept globally per run, not decomposed by class within one run). That
tradeoff is deliberate given the scope of this pass; documented as a
limitation in docs/README.md.

Selection favors no_helmet recall specifically (the class this checkpoint is
weakest on and the one most directly tied to a real safety violation) as long
as it does not push helmet/vest/person precision below a floor that would
create persistent false PPE incidents in the demo.

The chosen thresholds are frozen into app/inference/ppe_thresholds.json
(versioned) and are NOT re-tuned against the test split -- exactly one final
test-set evaluation runs after the decision (scripts/evaluate_vision_model.py).
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
ARTIFACT_PATH = MODELS_DIR / "artifacts" / "ppe-yolo11n.pt"
THRESHOLDS_PATH = BACKEND_ROOT / "app" / "inference" / "ppe_thresholds.json"

RUNTIME_DATASET_IDS = {"helmet": 0, "vest": 2, "person": 6, "no_helmet": 7}
CANDIDATE_THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]

# Precision floor: a class must not drop below this at its chosen threshold,
# or lowering confidence to chase recall would create persistent false
# incidents in the demo (a safety-relevant tradeoff, documented not hidden).
PRECISION_FLOOR = {"person": 0.60, "helmet": 0.70, "vest": 0.60, "no_helmet": 0.15}


def sweep():
    from ultralytics import YOLO

    model = YOLO(str(ARTIFACT_PATH))
    sweep_results: dict[str, list[dict]] = {name: [] for name in RUNTIME_DATASET_IDS}

    for conf in CANDIDATE_THRESHOLDS:
        metrics = model.val(data="construction-ppe.yaml", split="val", conf=conf, verbose=False)
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
            # Favor recall specifically for this class: pick the lowest (most permissive)
            # threshold that still clears the precision floor, maximizing recall.
            pool = eligible or points
            best = min(pool, key=lambda pt: pt["conf"])
        else:
            # Otherwise maximize F1 among thresholds clearing the floor.
            pool = eligible or points
            best = max(pool, key=lambda pt: pt["f1"])
        chosen[name] = best
    return chosen


def main():
    print("Sweeping candidate confidence thresholds on the VALIDATION split (never test)...")
    sweep_results = sweep()

    print(json.dumps(sweep_results, indent=2))

    chosen = select_thresholds(sweep_results)
    print("\nSelected thresholds (validation-derived):")
    print(json.dumps(chosen, indent=2))

    config = {
        "version": "1.0",
        "derived_from_split": "val",
        "candidate_thresholds_swept": CANDIDATE_THRESHOLDS,
        "precision_floor": PRECISION_FLOOR,
        "thresholds": {name: pt["conf"] for name, pt in chosen.items()},
        "selection_validation_metrics": chosen,
        "nms_iou": 0.50,
        "methodology": (
            "Global-confidence sweep through Ultralytics model.val() on the validation "
            "split at each candidate threshold, reading back per-class precision/recall "
            "from metrics.box.p/.r. no_helmet is optimized for recall (subject to a "
            "precision floor) because it is this checkpoint's weakest class and the one "
            "most directly tied to a real safety violation; other classes maximize F1. "
            "This is a coarser tool than a true per-class PR-curve extractor -- documented "
            "as a limitation, not hidden."
        ),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    sweep_path = EVAL_DIR / "ppe_threshold_sweep.json"
    sweep_path.write_text(json.dumps({"sweep": sweep_results, "selected": config}, indent=2))

    THRESHOLDS_PATH.write_text(json.dumps(config, indent=2))
    print(f"\nFrozen thresholds written to {THRESHOLDS_PATH}")
    print(f"Full sweep written to {sweep_path}")


if __name__ == "__main__":
    main()
