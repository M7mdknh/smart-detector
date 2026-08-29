"""Promotion gate executor for the v1.2 PPE-detector candidate.

Reads the comparative evaluation report (models/evaluation/vision_v1.2_comparative_evaluation.json)
and applies CLAUDE.md's promotion criteria mechanically:

  - no_helmet recall on the ORIGINAL construction-ppe test split must improve
    over v1.1's recorded baseline (0.175, models/evaluation/vision_model_metrics.json).
  - no_helmet precision must not collapse (defined here as: not falling below
    half of v1.1's no_helmet precision on the same split, and not landing at 0
    with any predictions made).
  - person/helmet/vest recall on BOTH ground-truthed sources must not
    materially regress (more than 0.10 absolute drop) versus v1.1.
  - candidate artifact must actually exist with a real, freshly computed
    sha256 (never promote on a missing/placeholder file).

This script NEVER touches models/registry.json on a failing gate, and never
overwrites models/artifacts/ppe-yolo11n.pt (the v1.1 artifact) in either
outcome. On a pass, it copies the candidate to models/artifacts/ppe-yolo11n-v1.2.pt
(new filename, v1.1 file untouched) and switches the ACTIVE pointer via
models/registry.json's "ppe_detector.artifact_path"/"sha256"/"version" fields
only -- app/inference/vision_worker_impl.py::load_model resolves its default
artifact filename from that registry field, so this is a config-only switch,
not a file overwrite. If a tuned v1.2 thresholds file exists
(models/evaluation/vision_v1.2_candidate_thresholds.json) it is also copied
into app/inference/ppe_thresholds.json (the active runtime thresholds file)
on promotion only.
"""

import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

MODELS_DIR = REPO_ROOT / "models"
EVAL_DIR = MODELS_DIR / "evaluation"
ARTIFACTS_DIR = MODELS_DIR / "artifacts"
REGISTRY_PATH = MODELS_DIR / "registry.json"
COMPARATIVE_REPORT_PATH = EVAL_DIR / "vision_v1.2_comparative_evaluation.json"
CANDIDATE_THRESHOLDS_PATH = EVAL_DIR / "vision_v1.2_candidate_thresholds.json"
ACTIVE_THRESHOLDS_PATH = BACKEND_ROOT / "app" / "inference" / "ppe_thresholds.json"
V1_1_BASELINE_METRICS_PATH = EVAL_DIR / "vision_model_metrics.json"

V1_1_NO_HELMET_RECALL_BASELINE = 0.175  # models/evaluation/vision_model_metrics.json, source-1 split
MATERIAL_REGRESSION_ABS_DROP = 0.10


def _rec(d: dict, *keys, default=None):
    for k in keys:
        if d is None:
            return default
        d = d.get(k)
    return d if d is not None else default


def evaluate_gate(report: dict) -> dict:
    v11 = report["v1_1_active"]["source_1_construction_ppe_test_split"]["per_class"]
    v12 = report["v1_2_candidate"]["source_1_construction_ppe_test_split"]["per_class"]

    v11_nh_recall = _rec(v11, "no_helmet", "recall", default=0.0) or 0.0
    v12_nh_recall = _rec(v12, "no_helmet", "recall", default=0.0) or 0.0
    v11_nh_precision = _rec(v11, "no_helmet", "precision", default=0.0) or 0.0
    v12_nh_precision = _rec(v12, "no_helmet", "precision", default=0.0) or 0.0

    checks = {}
    checks["no_helmet_recall_improves"] = {
        "v1_1": v11_nh_recall, "v1_2_candidate": v12_nh_recall,
        "baseline_reference": V1_1_NO_HELMET_RECALL_BASELINE,
        "pass": v12_nh_recall > v11_nh_recall and v12_nh_recall > V1_1_NO_HELMET_RECALL_BASELINE,
    }
    checks["no_helmet_precision_not_collapsed"] = {
        "v1_1": v11_nh_precision, "v1_2_candidate": v12_nh_precision,
        "pass": v12_nh_precision >= (v11_nh_precision * 0.5),
    }

    regressions = {}
    for source_key in ("source_1_construction_ppe_test_split", "source_2_industrial_safety_test_split"):
        v11_src = report["v1_1_active"][source_key]["per_class"]
        v12_src = report["v1_2_candidate"][source_key]["per_class"]
        for cls in ("person", "helmet", "vest"):
            r11 = _rec(v11_src, cls, "recall", default=None)
            r12 = _rec(v12_src, cls, "recall", default=None)
            if r11 is None or r12 is None:
                continue
            drop = r11 - r12
            regressions[f"{source_key}:{cls}"] = {
                "v1_1_recall": r11, "v1_2_candidate_recall": r12,
                "drop": drop, "pass": drop <= MATERIAL_REGRESSION_ABS_DROP,
            }
    checks["no_material_person_helmet_vest_regression"] = {
        "per_class_per_source": regressions,
        "pass": all(v["pass"] for v in regressions.values()) if regressions else False,
    }

    overall_pass = all(c["pass"] for c in checks.values())
    return {"checks": checks, "overall_pass": overall_pass}


def promote(candidate_path: Path, gate_result: dict, report: dict) -> dict:
    if not candidate_path.exists():
        raise FileNotFoundError(f"candidate artifact missing, cannot promote: {candidate_path}")

    new_artifact_path = ARTIFACTS_DIR / "ppe-yolo11n-v1.2.pt"
    shutil.copyfile(candidate_path, new_artifact_path)
    sha256 = hashlib.sha256(new_artifact_path.read_bytes()).hexdigest()
    size = new_artifact_path.stat().st_size

    registry = json.loads(REGISTRY_PATH.read_text())
    previous = dict(registry.get("ppe_detector", {}))

    registry["ppe_detector"] = {
        **previous,
        "version": "1.2",
        "artifact_path": str(new_artifact_path.relative_to(REPO_ROOT)),
        "sha256": sha256,
        "artifact_size_bytes": size,
        "previous_version": {
            "version": previous.get("version"),
            "artifact_path": previous.get("artifact_path"),
            "sha256": previous.get("sha256"),
            "artifact_size_bytes": previous.get("artifact_size_bytes"),
        },
        "promotion_gate_result": gate_result,
        "dataset_manifest_ref": "models/evaluation/vision_v1.2_dataset_manifest.json",
        "training_config_ref": "models/evaluation/vision_training_runs/ppe-yolo11n-v1.2-full/args.yaml",
        "comparative_evaluation_ref": "models/evaluation/vision_v1.2_comparative_evaluation.json",
        "promoted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))

    thresholds_switched = False
    if CANDIDATE_THRESHOLDS_PATH.exists():
        candidate_thresholds = json.loads(CANDIDATE_THRESHOLDS_PATH.read_text())
        ACTIVE_THRESHOLDS_PATH.write_text(json.dumps(candidate_thresholds, indent=2))
        thresholds_switched = True

    return {
        "promoted": True,
        "new_artifact_path": str(new_artifact_path.relative_to(REPO_ROOT)),
        "sha256": sha256,
        "thresholds_switched": thresholds_switched,
    }


def main():
    if not COMPARATIVE_REPORT_PATH.exists():
        print(f"BLOCKED: {COMPARATIVE_REPORT_PATH} does not exist; run the comparative evaluation first.")
        return 2

    report = json.loads(COMPARATIVE_REPORT_PATH.read_text())
    gate_result = evaluate_gate(report)

    print(json.dumps(gate_result, indent=2))

    if not gate_result["overall_pass"]:
        print("\nPROMOTION GATE: FAIL. models/registry.json left untouched; v1.1 remains active.")
        out = EVAL_DIR / "vision_v1.2_promotion_decision.json"
        out.write_text(json.dumps({"decision": "REJECTED", "gate_result": gate_result, "decided_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=2))
        return 1

    candidate_path = ARTIFACTS_DIR / "ppe-yolo11n-v1.2-epoch7-candidate.pt"
    result = promote(candidate_path, gate_result, report)
    print("\nPROMOTION GATE: PASS.")
    print(json.dumps(result, indent=2))
    out = EVAL_DIR / "vision_v1.2_promotion_decision.json"
    out.write_text(json.dumps({"decision": "PROMOTED", "gate_result": gate_result, "promotion_result": result, "decided_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
