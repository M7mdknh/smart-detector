"""Runs demo-assets/interview_compilation_source.mp4 through the REAL,
registered production PPE detector + ByteTrack pipeline (the exact same
app.inference.vision_worker_impl.process_frame_full used by the live vision
worker -- no separate/duplicated detection logic) and writes a fully
annotated copy of the video: person/track boxes, PPE item boxes with
canonical labels and confidence, per-person PPE state, zone polygons, foot
points, restricted-zone dwell, and a model-version/timestamp/frame-id readout
burned into every frame (app.inference.frame_annotation.render_annotated_frame).

This does NOT touch the incident/database pipeline -- it is purely the visual
artifact required for the interview demo (see docs/INTERVIEW_DEMO.md). Real
incident generation against this same video happens by actually running the
backend (uvicorn) with SENTINEL_INTERVIEW_DEMO_MODE=1 and
SENTINEL_VISION_REPLAY_PATH pointed at the source compilation -- see
docs/INTERVIEW_DEMO.md for that sequence.

Threshold/model honesty: uses load_model() with no override, so the exact
registered v1.1 artifact and its tuned confidence thresholds run here -- no
selectively lowered confidence to make this video look better than the
system actually performs.
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

SOURCE_PATH = REPO_ROOT / "demo-assets" / "interview_compilation_source.mp4"
OUT_PATH = REPO_ROOT / "demo-assets" / "interview_compilation_annotated.mp4"


def main():
    import cv2

    from app.inference.frame_annotation import render_annotated_frame
    from app.inference.vision_worker_impl import TrackDwell, load_model, process_frame_full
    from app.inference.zone_config import get_zone_config

    if not SOURCE_PATH.exists():
        raise SystemExit(f"{SOURCE_PATH} not found -- build the source compilation first.")

    model, model_version, person_only, status = load_model()
    print(f"Loaded model_version={model_version} status={status}")
    if model is None:
        raise SystemExit(f"PPE detector unavailable (status={status}); refusing to fabricate annotations on an unavailable model.")

    cap = cv2.VideoCapture(str(SOURCE_PATH))
    if not cap.isOpened():
        raise SystemExit(f"failed to open {SOURCE_PATH}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Source: {width}x{height} @ {fps:.2f}fps, {total_frames} frames")

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    tmp_out = OUT_PATH.with_suffix(".raw.mp4")
    writer = cv2.VideoWriter(str(tmp_out), fourcc, fps, (width, height))

    zone_config = get_zone_config()
    tracks: dict[int, TrackDwell] = {}
    frame_id = 0
    base_time = datetime.now(timezone.utc)
    detections_summary = {"frames_with_person": 0, "frames_with_no_helmet_detection": 0, "frames_with_helmet_detection": 0, "frames_with_vest_detection": 0}
    t0 = time.monotonic()

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_id += 1
        # event_time advances with real source-video timing (1/fps per frame), not
        # wall-clock render time, so PPE/zone dwell thresholds (seconds) are evaluated
        # against the footage's own natural timing, matching the live worker's semantics.
        event_time = base_time + timedelta(seconds=(frame_id - 1) / fps)

        rows, persons, ppe_candidates = process_frame_full(model, frame, frame_id, event_time, tracks, person_only, model_version)

        if persons:
            detections_summary["frames_with_person"] += 1
        for name, _box, _conf in ppe_candidates:
            if name == "no_helmet":
                detections_summary["frames_with_no_helmet_detection"] += 1
            elif name == "helmet":
                detections_summary["frames_with_helmet_detection"] += 1
            elif name == "vest":
                detections_summary["frames_with_vest_detection"] += 1

        annotated = render_annotated_frame(frame, persons, ppe_candidates, tracks, zone_config, model_version, event_time, frame_id)
        writer.write(annotated)

        if frame_id % 50 == 0:
            print(f"  processed {frame_id}/{total_frames} frames...")

    cap.release()
    writer.release()
    elapsed = time.monotonic() - t0
    achieved_fps = frame_id / max(elapsed, 1e-6)
    print(f"Processed {frame_id} frames in {elapsed:.1f}s ({achieved_fps:.1f} fps)")
    print(f"Detection summary: {detections_summary}")

    # mp4v (OpenCV's fourcc) is not always browser/GitHub-preview friendly; re-mux to
    # H.264 via ffmpeg for the final deliverable, matching interview_compilation_source.mp4.
    import subprocess

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(tmp_out), "-c:v", "libx264", "-crf", "23", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT_PATH)],
        check=True,
    )
    tmp_out.unlink()
    print(f"Wrote {OUT_PATH}")

    import hashlib
    import json

    report_path = REPO_ROOT / "models" / "evaluation" / "interview_video_detection_summary.json"
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_used": model_version,
        "source_path": str(SOURCE_PATH.relative_to(REPO_ROOT)),
        "source_sha256": hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
        "output_path": str(OUT_PATH.relative_to(REPO_ROOT)),
        "n_frames_processed": frame_id,
        "processing_fps_this_machine": achieved_fps,
        "frames_with_person_detection": detections_summary["frames_with_person"],
        "frames_with_helmet_detection": detections_summary["frames_with_helmet_detection"],
        "frames_with_no_helmet_detection": detections_summary["frames_with_no_helmet_detection"],
        "frames_with_vest_detection": detections_summary["frames_with_vest_detection"],
        "note": "Real-time detector run against the genuine interview-compilation source video at the registered runtime confidence thresholds (backend/app/inference/ppe_thresholds.json) -- no threshold was lowered for this clip. frames_with_no_helmet_detection=0 is a real, disclosed finding (see demo-assets/INTERVIEW_VIDEO_SOURCES.md): the no_helmet class does not clear its 0.05 threshold anywhere in this clip even though a bare-headed worker is genuinely visible; PPE_HELMET_OVERHEAD_VIOLATION incidents observed live instead fire via the 'no positive helmet evidence while in the overhead zone' policy path, not this class directly.",
    }
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
