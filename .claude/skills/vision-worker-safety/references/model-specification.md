# Vision Model Specification

Read this reference when preparing data, training/exporting YOLO, implementing inference/tracking/PPE association, or evaluating camera-derived events.

## Dataset and Classes

Use the credential-free Ultralytics Construction-PPE dataset with its published train/validation/test split. Record dataset checksum, retrieval URL, access date, and AGPL-3.0 licence. Runtime classes:

| Dataset class | Runtime class | Use |
|---|---|---|
| `Person` | `person` | Track and zone membership |
| `helmet` | `helmet` | Positive helmet evidence |
| `vest` | `vest` | Positive vest evidence |
| `no_helmet` | `no_helmet` | Negative helmet evidence |

Ignore other classes at runtime; do not relabel them as safe/unsafe. Because the source dataset has no `no_vest`, missing-vest status must be inferred by persistent failed association and begins as `UNKNOWN`.

Keep the published test split untouched. Add a small separately labelled factory-like replay set for honest domain-gap evaluation, not training, if licensing permits.

## Detector

- Base: COCO-pretrained `yolo11n.pt`.
- Input: letterboxed RGB, 640x640.
- Initial training: 60 epochs, patience 12, batch 16 or lower if hardware requires, seed 42, default Ultralytics augmentation recorded in the run config.
- Selection: checkpoint with best validation mAP50-95, subject to person and helmet recall review.
- Runtime artifact: `models/artifacts/ppe-yolo11n.pt` with SHA-256 in the registry.
- Runtime target: bundled replay works on CPU; GPU is optional.
- Training is an offline command and never runs during `make demo`.

Initial class confidence thresholds, tuned later on validation data:

- person `0.35`;
- helmet `0.25`;
- vest `0.30`;
- no_helmet `0.25`;
- NMS IoU `0.50`.

Use class-specific thresholds in configuration. Do not describe these initial values as validated until evaluation is recorded.

## Frame Processing

- Default demo source: bundled/licensed video; optional webcam is selected explicitly.
- Target inference cadence: up to 10 frames/second. When overloaded, drop stale frames rather than queueing increasing latency.
- Preserve source timestamp, frame sequence, source type, camera ID, and model version.
- Store structured detections/evidence. Do not store live raw frames in SQLite.
- Annotated preview may be an in-memory MJPEG/WebSocket frame stream or a server endpoint; it must derive overlays from the same emitted evidence.

## ByteTrack Defaults

Use a checked-in tracker config and record its version:

```text
track_high_thresh=0.45
track_low_thresh=0.10
new_track_thresh=0.50
track_buffer=30
match_thresh=0.80
fuse_score=true
```

Treat these as starting values. Dwell uses timestamps, so frame-rate changes do not alter policy time. Track IDs are session-local and must not be presented as employee identity.

## Per-Person Association

For each person box `(x1,y1,x2,y2)`:

- head region: upper 35% of the box, expanded 10% horizontally;
- torso region: vertical 25–75% and horizontal 10–90% of the person box;
- helmet/no-helmet candidate: centre within head region, then highest confidence/overlap;
- vest candidate: centre within torso region, then highest confidence/overlap;
- zone point: bottom-centre `(0.5*(x1+x2), y2)` in normalized image coordinates.

If two persons compete for one PPE box, assign at most once using the best normalized overlap/centre-distance score. Keep state `UNKNOWN` under severe overlap or ambiguous assignment.

## Temporal State

Maintain timestamped evidence per track:

- enter a zone after 2 seconds of persistent inside evidence;
- exit after 2 seconds of persistent outside evidence;
- helmet `NON_COMPLIANT` after `no_helmet` persists for 3 seconds, or no helmet is associated for 3 seconds in an overhead zone with adequate head visibility;
- vest `NON_COMPLIANT` after no vest is associated for 3 seconds in a mandatory-vest zone with adequate torso visibility;
- positive helmet/vest evidence sets `COMPLIANT` after 1 second;
- conflicting/occluded evidence returns `UNKNOWN`, not compliant;
- clear a violation only after 5 seconds of compliant/outside evidence.

All durations are configuration values. The risk engine, not the detector, decides incident severity.

## Zone Configuration

Store polygons in normalized camera coordinates with config version. Validate simple non-self-intersecting polygons with at least three points. Provide one gas-exposure polygon and one overhead-work polygon in P0. Render the exact configured polygons on the preview.

## Degraded Behavior

- End-of-file loops only when replay mode says loop; label replay clearly.
- No frame within two expected intervals -> camera `DEGRADED`.
- Model timeout/load failure -> model `UNAVAILABLE`; stop making fresh compliance claims.
- Tracker failure -> emit boxes with null track IDs and do not open per-track dwell incidents.
- Simulation ground truth may keep the simulator demo functional but is displayed with its own provenance, never as replacement CV evidence.

## Evaluation

Report:

- per-class precision, recall, AP50, and AP50-95 on the untouched dataset test split;
- event-level helmet and vest violation precision/recall/F1 after temporal association;
- person/helmet recall separately because missed safety evidence matters;
- ID switches or track fragmentation on a small labelled clip;
- end-to-end median/p95 frame latency and achieved FPS on declared hardware;
- error slices: small helmets, partial occlusion, multiple people, poor lighting, and factory-domain replay.

Document that construction PPE data does not prove factory performance. Do not claim production readiness from source-dataset mAP alone.
