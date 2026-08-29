"""Phase 9: qualitative tracking/domain-gap stress test on the secondary
natural-motion clip (demo-assets/replay_natural_motion.mp4, see
demo-assets/NATURAL_MOTION_SOURCE.md for licence/provenance).

Reported SEPARATELY from the official Construction-PPE test-split metrics
(scripts/evaluate_vision_model.py) -- this is not a benchmark, there is no
ground-truth annotation for this clip. It reports what the real detector
actually produced against real continuous motion: detection counts,
track-ID continuity, and per-frame confidence, so a reviewer can judge the
construction-to-factory domain gap qualitatively.
"""

import json
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

EVAL_DIR = REPO_ROOT / "models" / "evaluation"
CLIP_PATH = REPO_ROOT / "demo-assets" / "replay_natural_motion.mp4"


def main():
    import cv2

    from app.inference.vision_worker_impl import TrackDwell, load_model, process_frame

    if not CLIP_PATH.exists():
        print(f"SKIPPED: {CLIP_PATH} not present.")
        report = {"status": "SKIPPED", "reason": "asset not present"}
        EVAL_DIR.mkdir(parents=True, exist_ok=True)
        (EVAL_DIR / "natural_motion_report.json").write_text(json.dumps(report, indent=2))
        return

    model, model_version, person_only = load_model()
    if person_only:
        print("NOTE: fine-tuned PPE artifact unavailable; running COCO fallback (person-only).")

    cap = cv2.VideoCapture(str(CLIP_PATH))
    tracks: dict[int, TrackDwell] = {}
    from datetime import datetime, timedelta, timezone

    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

    frame_id = 0
    person_confidences = []
    ppe_class_counts = {"helmet": 0, "no_helmet": 0, "vest": 0}
    track_frame_counts: dict[int, int] = {}
    id_switch_events = 0
    prev_ids: set[int] = set()
    latencies = []

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_id += 1
        event_time = t0 + timedelta(seconds=frame_id * 0.2)

        t_start = time.perf_counter()
        rows = process_frame(model, frame, frame_id, event_time, tracks, person_only, model_version)
        latencies.append(time.perf_counter() - t_start)

        current_ids = set()
        for r in rows:
            if r.detected_class == "person":
                person_confidences.append(r.confidence)
                if r.track_id is not None:
                    current_ids.add(r.track_id)
                    track_frame_counts[r.track_id] = track_frame_counts.get(r.track_id, 0) + 1
            elif r.detected_class in ppe_class_counts:
                ppe_class_counts[r.detected_class] += 1

        if prev_ids and current_ids and not (prev_ids & current_ids):
            id_switch_events += 1
        prev_ids = current_ids

    cap.release()

    import numpy as np

    report = {
        "status": "OK",
        "clip": str(CLIP_PATH.relative_to(REPO_ROOT)),
        "model_used": model_version,
        "person_only_fallback": person_only,
        "n_frames_processed": frame_id,
        "person_detections": len(person_confidences),
        "person_detection_rate": len(person_confidences) / frame_id if frame_id else 0,
        "person_mean_confidence": float(np.mean(person_confidences)) if person_confidences else None,
        "unique_track_ids": len(track_frame_counts),
        "id_switch_candidate_events": id_switch_events,
        "ppe_class_frame_counts": ppe_class_counts,
        "latency_ms_median": float(np.median(latencies) * 1000) if latencies else None,
        "note": (
            "Qualitative stress test on a real continuous-motion clip, NOT a benchmark -- "
            "no ground-truth annotation exists for this clip. Compare person_detection_rate "
            "and PPE class counts against the official Construction-PPE test-split numbers in "
            "vision_model_metrics.json to judge the construction-to-factory / domain-shift gap "
            "qualitatively, not as a paired metric."
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVAL_DIR / "natural_motion_report.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
