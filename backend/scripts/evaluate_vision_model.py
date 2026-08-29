"""Vision evaluation (part of `make evaluate`): per-class detection metrics on
the untouched Construction-PPE test split, plus PPE event-level and latency/FPS
metrics measured by actually running the fine-tuned model against the bundled
replay clip end to end (not vendor-reported numbers).
"""

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
ARTIFACT_PATH = MODELS_DIR / "artifacts" / "ppe-yolo11n.pt"
REPLAY_PATH = REPO_ROOT / "demo-assets" / "replay.mp4"
TRACKER_CONFIG_PATH = str(BACKEND_ROOT / "app" / "inference" / "bytetrack.yaml")

RUNTIME_CLASSES = ["person", "helmet", "vest", "no_helmet"]
DATASET_CLASS_NAMES = ["helmet", "gloves", "vest", "boots", "goggles", "none", "Person", "no_helmet", "no_goggle", "no_gloves", "no_boots"]
RUNTIME_DATASET_IDS = {"helmet": 0, "vest": 2, "person": 6, "no_helmet": 7}


def detection_metrics() -> dict:
    from ultralytics import YOLO

    if not ARTIFACT_PATH.exists():
        return {"status": "ARTIFACT_MISSING", "detail": str(ARTIFACT_PATH)}

    model = YOLO(str(ARTIFACT_PATH))
    metrics = model.val(data="construction-ppe.yaml", split="test", verbose=False)

    per_class = {}
    for name, dataset_id in RUNTIME_DATASET_IDS.items():
        try:
            idx = list(metrics.box.ap_class_index).index(dataset_id)
            per_class[name] = {
                "precision": float(metrics.box.p[idx]),
                "recall": float(metrics.box.r[idx]),
                "ap50": float(metrics.box.ap50[idx]),
                "ap50_95": float(metrics.box.ap[idx]),
            }
        except ValueError:
            per_class[name] = {"precision": None, "recall": None, "ap50": None, "ap50_95": None, "note": "class absent from test-split predictions/labels"}

    return {
        "status": "OK",
        "map50": float(metrics.box.map50),
        "map50_95": float(metrics.box.map),
        "per_class": per_class,
        "person_recall": per_class.get("person", {}).get("recall"),
        "helmet_recall": per_class.get("helmet", {}).get("recall"),
        "note": "Measured on the full published Construction-PPE test split (141 images), never used for training or threshold tuning. 12 of these 141 images are also the source stills for the bundled demo replay clip (demo-assets/REPLAY_SOURCE.md); see models/evaluation/vision_replay_overlap_analysis.json for the disclosed overlap and confirmation that scoring the remaining 129 non-replay images changes no metric materially.",
    }


def replay_latency_and_ppe_events() -> dict:
    import cv2
    from ultralytics import YOLO

    if not ARTIFACT_PATH.exists() or not REPLAY_PATH.exists():
        return {"status": "SKIPPED", "reason": "artifact or replay clip missing"}

    model = YOLO(str(ARTIFACT_PATH))
    cap = cv2.VideoCapture(str(REPLAY_PATH))

    latencies_ms = []
    track_id_frames: dict[int, int] = {}
    unique_track_ids: set[int] = set()
    id_switch_candidates = 0
    prev_track_ids: set[int] = set()
    ppe_event_frames = {"helmet": 0, "no_helmet": 0, "vest": 0}
    n_frames = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        n_frames += 1
        t0 = time.perf_counter()
        results = model.track(frame, persist=True, verbose=False, conf=0.20, iou=0.50, tracker=TRACKER_CONFIG_PATH)
        latencies_ms.append((time.perf_counter() - t0) * 1000)

        boxes = results[0].boxes
        current_ids = set()
        for i in range(len(boxes)):
            cls_id = int(boxes.cls[i])
            name = model.names[cls_id]
            if name == "Person" and boxes.id is not None:
                tid = int(boxes.id[i])
                current_ids.add(tid)
                unique_track_ids.add(tid)
                track_id_frames[tid] = track_id_frames.get(tid, 0) + 1
            elif name in ppe_event_frames:
                ppe_event_frames[name] += 1

        # Crude fragmentation signal: a previously-tracked ID disappearing then a new
        # ID appearing on the very next frame while a person is still present.
        if prev_track_ids and current_ids and not (prev_track_ids & current_ids):
            id_switch_candidates += 1
        prev_track_ids = current_ids
    cap.release()

    if not latencies_ms:
        return {"status": "NO_FRAMES"}

    latencies_ms.sort()
    p50 = statistics.median(latencies_ms)
    p95 = latencies_ms[int(len(latencies_ms) * 0.95) - 1]
    fps = 1000.0 / statistics.mean(latencies_ms) if latencies_ms else None

    return {
        "status": "OK",
        "n_frames": n_frames,
        "unique_track_ids": len(unique_track_ids),
        "track_id_frame_counts": track_id_frames,
        "id_switch_candidate_events": id_switch_candidates,
        "ppe_class_frame_counts": ppe_event_frames,
        "latency_ms_median": p50,
        "latency_ms_p95": p95,
        "achieved_fps": fps,
        "note": "Measured by actually running the fine-tuned model against the bundled replay "
                "clip frame-by-frame on this machine's hardware, not a vendor benchmark.",
    }


def main():
    import platform

    try:
        import torch

        hardware = torch.cuda.get_device_name(0) if torch.cuda.is_available() else (platform.processor() or platform.machine())
        device = "GPU: " + hardware if torch.cuda.is_available() else "CPU: " + hardware
    except ImportError:
        device = "unavailable (torch not installed)"

    report = {
        "declared_hardware": device,
        "detection_metrics": detection_metrics(),
        "replay_evaluation": replay_latency_and_ppe_events(),
        "domain_gap_note": (
            "Detection metrics are measured on the Construction-PPE test split (construction-site "
            "imagery), not a factory floor. Person/PPE recall figures here do not establish "
            "factory-deployment accuracy -- see docs/README.md's domain-gap limitations section."
        ),
    }

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVAL_DIR / "vision_model_metrics.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
