"""Comparative evaluation: v1.1 (active) vs v1.2-candidate PPE detector.

Standalone script, separate from `make evaluate`'s evaluate_vision_model.py
(which is the maintained, single-artifact production evaluation path and is
NOT modified by this script). This script exists only for the one-time
promotion-gate comparison and is not part of any Makefile target.

Both artifacts are evaluated on IDENTICAL inputs per source, and results are
reported SEPARATELY per source (never blended into one headline number):

  1. Original Construction-PPE test split (141 images, untouched, 11-class
     raw labels) -- ground truth filtered/remapped to the 4 shared runtime
     classes (person/helmet/vest/no_helmet) via each artifact's own
     dataset-to-runtime class-name mapping.
  2. The new Industrial-Safety dataset's own held-out test split
     (external-data/converted_dataset/test -- already in canonical
     person/helmet/vest/no_helmet order).
  3. The bundled replay clip (demo-assets/replay.mp4) -- event-level
     PPE/tracking behaviour, no ground truth.
  4. The natural-motion clip (demo-assets/replay_natural_motion.mp4) --
     qualitative domain-gap stress test, no ground truth.

Because v1.1 (11 native classes) and v1.2-candidate (4 native classes) do not
share an output space, per-image detection metrics are computed with a
custom IoU-matching evaluator (greedy, IoU>=0.5, confidence-sorted) applied
identically to both models' predictions after normalizing box class names to
the 4 canonical runtime classes -- NOT ultralytics' model.val(), which
requires matching nc between model and data.yaml and cannot compare two
different-nc models on one dataset.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

MODELS_DIR = REPO_ROOT / "models"
EVAL_DIR = MODELS_DIR / "evaluation"
ARTIFACTS_DIR = MODELS_DIR / "artifacts"

V1_1_PATH = ARTIFACTS_DIR / "ppe-yolo11n.pt"
V1_2_CANDIDATE_PATH = ARTIFACTS_DIR / "ppe-yolo11n-v1.2-epoch7-candidate.pt"

CONSTRUCTION_PPE_ROOT = Path.home() / "datasets" / "construction-ppe"
INDUSTRIAL_SAFETY_TEST_ROOT = REPO_ROOT / "external-data" / "converted_dataset" / "test"

REPLAY_PATH = REPO_ROOT / "demo-assets" / "replay.mp4"
NATURAL_MOTION_PATH = REPO_ROOT / "demo-assets" / "replay_natural_motion.mp4"
TRACKER_CONFIG_PATH = str(BACKEND_ROOT / "app" / "inference" / "bytetrack.yaml")

CANONICAL_CLASSES = ["person", "helmet", "vest", "no_helmet"]
# Spec-default per-class confidence thresholds (app/inference/vision_worker_impl.py
# falls back to these if no tuned thresholds file is present). Each artifact below
# is evaluated at ITS OWN validation-derived tuned thresholds where available
# (see load_thresholds_for), not necessarily these defaults.
_SPEC_DEFAULT_THRESHOLDS = {"person": 0.35, "helmet": 0.25, "vest": 0.30, "no_helmet": 0.25}
V1_1_THRESHOLDS_PATH = BACKEND_ROOT / "app" / "inference" / "ppe_thresholds.json"
V1_2_CANDIDATE_THRESHOLDS_PATH = EVAL_DIR / "vision_v1.2_candidate_thresholds.json"
NMS_IOU = 0.50


def load_thresholds_for(label: str) -> dict:
    """Loads the validation-derived tuned thresholds actually associated with
    the given artifact label, falling back to the P0 spec defaults if the
    tuned-thresholds file is missing (never fabricated)."""
    path = V1_1_THRESHOLDS_PATH if "v1.1" in label else V1_2_CANDIDATE_THRESHOLDS_PATH
    if path.exists():
        try:
            data = json.loads(path.read_text())
            thresholds = data.get("thresholds", {})
            if set(thresholds) == set(_SPEC_DEFAULT_THRESHOLDS):
                return {k: float(v) for k, v in thresholds.items()}
        except Exception:
            pass
    return dict(_SPEC_DEFAULT_THRESHOLDS)
MATCH_IOU_THRESHOLD = 0.50

# Construction-PPE raw class name -> canonical runtime class name (only the 4 in scope; others ignored).
CONSTRUCTION_PPE_NAME_MAP = {"Person": "person", "helmet": "helmet", "vest": "vest", "no_helmet": "no_helmet"}
# Industrial-safety (v1.2) model already outputs canonical lowercase names directly.
INDUSTRIAL_SAFETY_NAME_MAP = {"person": "person", "helmet": "helmet", "vest": "vest", "no_helmet": "no_helmet"}


def iou_xyxy(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def load_yolo_labels(label_path: Path, img_w: int, img_h: int, raw_id_to_canonical_name: dict) -> list[tuple[str, tuple]]:
    """Returns list of (canonical_class_name, xyxy_pixels) for boxes whose raw
    class id maps to one of the 4 canonical runtime classes; other classes'
    boxes are silently dropped (matches the runtime's own scope filter)."""
    boxes = []
    if not label_path.exists():
        return boxes
    for line in label_path.read_text().splitlines():
        parts = line.split()
        if not parts:
            continue
        raw_id = int(parts[0])
        if raw_id not in raw_id_to_canonical_name:
            continue
        name = raw_id_to_canonical_name[raw_id]
        cx, cy, w, h = (float(v) for v in parts[1:5])
        x1 = (cx - w / 2) * img_w
        y1 = (cy - h / 2) * img_h
        x2 = (cx + w / 2) * img_w
        y2 = (cy + h / 2) * img_h
        boxes.append((name, (x1, y1, x2, y2)))
    return boxes


def voc_ap(recalls: list[float], precisions: list[float]) -> float:
    """Standard 11-point-free VOC-style AP: area under the precision-envelope
    (monotonically non-increasing) recall curve."""
    if not recalls:
        return 0.0
    mrec = [0.0] + recalls + [1.0]
    mpre = [0.0] + precisions + [0.0]
    for i in range(len(mpre) - 2, -1, -1):
        mpre[i] = max(mpre[i], mpre[i + 1])
    ap = 0.0
    for i in range(1, len(mrec)):
        ap += (mrec[i] - mrec[i - 1]) * mpre[i]
    return ap


def evaluate_detector_on_split(model_path: Path, images_dir: Path, labels_dir: Path, raw_id_to_canonical_name: dict, name_normalize: dict, conf_thresholds: dict) -> dict:
    import cv2
    from ultralytics import YOLO

    if not model_path.exists():
        return {"status": "ARTIFACT_MISSING", "detail": str(model_path)}
    if not images_dir.exists():
        return {"status": "DATA_MISSING", "detail": str(images_dir)}

    model = YOLO(str(model_path))
    image_paths = sorted([p for p in images_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")])

    # Per-class prediction records: (confidence, is_tp) built after greedy matching, plus running gt counts.
    gt_counts = {c: 0 for c in CANONICAL_CLASSES}
    preds_by_class: dict[str, list[tuple[float, bool]]] = {c: [] for c in CANONICAL_CLASSES}

    for img_path in image_paths:
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        h, w = img.shape[:2]
        label_path = labels_dir / (img_path.stem + ".txt")
        gt_boxes = load_yolo_labels(label_path, w, h, raw_id_to_canonical_name)
        for name, _ in gt_boxes:
            gt_counts[name] += 1
        gt_matched = [False] * len(gt_boxes)

        results = model.predict(img, verbose=False, conf=0.05, iou=NMS_IOU)
        boxes = results[0].boxes
        preds = []
        for i in range(len(boxes)):
            raw_name = model.names[int(boxes.cls[i])]
            canon = name_normalize.get(raw_name)
            if canon is None:
                continue
            conf = float(boxes.conf[i])
            if conf < conf_thresholds.get(canon, 0.25):
                continue
            xy = tuple(float(v) for v in boxes.xyxy[i])
            preds.append((canon, conf, xy))
        # Sort predictions by confidence descending for greedy matching (VOC-style).
        preds.sort(key=lambda t: -t[1])

        for canon, conf, box in preds:
            best_iou, best_j = 0.0, -1
            for j, (gname, gbox) in enumerate(gt_boxes):
                if gname != canon or gt_matched[j]:
                    continue
                iou = iou_xyxy(box, gbox)
                if iou > best_iou:
                    best_iou, best_j = iou, j
            is_tp = best_iou >= MATCH_IOU_THRESHOLD
            if is_tp:
                gt_matched[best_j] = True
            preds_by_class[canon].append((conf, is_tp))

    per_class = {}
    for c in CANONICAL_CLASSES:
        records = sorted(preds_by_class[c], key=lambda t: -t[0])
        n_gt = gt_counts[c]
        tp_cum, fp_cum = 0, 0
        recalls, precisions = [], []
        for conf, is_tp in records:
            if is_tp:
                tp_cum += 1
            else:
                fp_cum += 1
            recalls.append(tp_cum / n_gt if n_gt else 0.0)
            precisions.append(tp_cum / (tp_cum + fp_cum))
        ap50 = voc_ap(recalls, precisions) if n_gt else (0.0 if records else None)
        final_tp = sum(1 for _, is_tp in records if is_tp)
        per_class[c] = {
            "gt_count": n_gt,
            "n_predictions_at_runtime_threshold": len(records),
            "precision": (final_tp / len(records)) if records else (None if n_gt == 0 else 0.0),
            "recall": (final_tp / n_gt) if n_gt else None,
            "ap50": ap50,
        }

    return {
        "status": "OK",
        "n_images": len(image_paths),
        "per_class": per_class,
        "method": "custom greedy IoU>=0.5 matching at runtime per-class confidence thresholds, VOC-style AP50; NOT ultralytics model.val() (incompatible nc between v1.1 11-class and v1.2 4-class models)",
    }


def video_event_evaluation(model_path: Path, video_path: Path) -> dict:
    import cv2
    from ultralytics import YOLO

    if not model_path.exists() or not video_path.exists():
        return {"status": "SKIPPED", "reason": "artifact or clip missing"}

    model = YOLO(str(model_path))
    cap = cv2.VideoCapture(str(video_path))

    latencies_ms = []
    track_id_frames: dict[int, int] = {}
    unique_track_ids: set[int] = set()
    id_switch_candidates = 0
    prev_track_ids: set[int] = set()
    ppe_class_frames = {"helmet": 0, "no_helmet": 0, "vest": 0}
    n_frames = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        n_frames += 1
        t0 = time.perf_counter()
        results = model.track(frame, persist=True, verbose=False, conf=0.20, iou=NMS_IOU, tracker=TRACKER_CONFIG_PATH)
        latencies_ms.append((time.perf_counter() - t0) * 1000)

        boxes = results[0].boxes
        current_ids = set()
        for i in range(len(boxes)):
            raw_name = model.names[int(boxes.cls[i])]
            name = {"Person": "person", "person": "person"}.get(raw_name, raw_name)
            if name == "person" and boxes.id is not None:
                tid = int(boxes.id[i])
                current_ids.add(tid)
                unique_track_ids.add(tid)
                track_id_frames[tid] = track_id_frames.get(tid, 0) + 1
            elif raw_name in ppe_class_frames:
                ppe_class_frames[raw_name] += 1
        if prev_track_ids and current_ids and not (prev_track_ids & current_ids):
            id_switch_candidates += 1
        prev_track_ids = current_ids
    cap.release()

    if not latencies_ms:
        return {"status": "NO_FRAMES"}

    latencies_ms.sort()
    p50 = statistics.median(latencies_ms)
    p95 = latencies_ms[int(len(latencies_ms) * 0.95) - 1]
    fps = 1000.0 / statistics.mean(latencies_ms)

    return {
        "status": "OK",
        "n_frames": n_frames,
        "unique_track_ids": len(unique_track_ids),
        "id_switch_candidate_events": id_switch_candidates,
        "ppe_class_frame_counts": ppe_class_frames,
        "latency_ms_median": p50,
        "latency_ms_p95": p95,
        "achieved_fps": fps,
    }


def evaluate_artifact(model_path: Path, label: str) -> dict:
    print(f"\n=== Evaluating {label}: {model_path} ===", file=sys.stderr)
    result = {"artifact_path": str(model_path.relative_to(REPO_ROOT)) if model_path.exists() else str(model_path)}
    if model_path.exists():
        import hashlib

        result["sha256"] = hashlib.sha256(model_path.read_bytes()).hexdigest()

    conf_thresholds = load_thresholds_for(label)
    result["conf_thresholds_used"] = conf_thresholds

    print("  source 1: original construction-ppe test split...", file=sys.stderr)
    result["source_1_construction_ppe_test_split"] = evaluate_detector_on_split(
        model_path,
        CONSTRUCTION_PPE_ROOT / "images" / "test",
        CONSTRUCTION_PPE_ROOT / "labels" / "test",
        {0: "helmet", 2: "vest", 6: "person", 7: "no_helmet"},
        CONSTRUCTION_PPE_NAME_MAP,
        conf_thresholds,
    )

    print("  source 2: industrial-safety (v1.2) own test split...", file=sys.stderr)
    result["source_2_industrial_safety_test_split"] = evaluate_detector_on_split(
        model_path,
        INDUSTRIAL_SAFETY_TEST_ROOT / "images",
        INDUSTRIAL_SAFETY_TEST_ROOT / "labels",
        {0: "person", 1: "helmet", 2: "vest", 3: "no_helmet"},
        INDUSTRIAL_SAFETY_NAME_MAP,
        conf_thresholds,
    )

    print("  source 3: bundled replay clip...", file=sys.stderr)
    result["source_3_bundled_replay_clip"] = video_event_evaluation(model_path, REPLAY_PATH)

    print("  source 4: natural-motion clip...", file=sys.stderr)
    result["source_4_natural_motion_clip"] = video_event_evaluation(model_path, NATURAL_MOTION_PATH)

    result["source_5_other_bundled_video"] = {
        "status": "NOT_APPLICABLE",
        "note": "demo-assets/ contains only replay.mp4 (source 3) and replay_natural_motion.mp4 (source 4). No other continuous video is legally bundled in this repo; nothing invented.",
    }
    return result


def main():
    import platform

    try:
        import torch

        hardware = torch.cuda.get_device_name(0) if torch.cuda.is_available() else (platform.processor() or platform.machine())
        gpu_available = torch.cuda.is_available()
        torch_version = torch.__version__
    except ImportError:
        hardware, gpu_available, torch_version = "unavailable", False, None

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "declared_hardware": hardware,
        "gpu_available": gpu_available,
        "torch_version": torch_version,
        "v1_1_active": evaluate_artifact(V1_1_PATH, "v1.1 (active)"),
        "v1_2_candidate": evaluate_artifact(V1_2_CANDIDATE_PATH, "v1.2-candidate"),
        "note": "Metrics reported SEPARATELY per source, never blended. Sources 1-2 are ground-truthed "
                "detection metrics (custom IoU-matching evaluator, identical methodology for both "
                "artifacts). Sources 3-4 are event-level/tracking behaviour on real continuous video, "
                "no ground truth available.",
    }

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVAL_DIR / "vision_v1.2_comparative_evaluation.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
