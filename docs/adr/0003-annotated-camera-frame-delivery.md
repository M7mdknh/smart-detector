# ADR 0003: Annotated camera frame delivery to the dashboard

Status: **EXECUTED** (assessment-submission-v3.0).

## Context

Before this change, `GET /api/v1/vision/latest` gave the dashboard's camera
panel only structured detection data (per-track class/confidence/PPE-state
JSON) plus a client-rendered SVG zone overlay. The rendering pipeline that
burns real boxes/labels/track IDs/zone polygons onto actual decoded replay
pixels already existed (`app/inference/frame_annotation.py`,
`app/inference/frame_cache.py`) but was only invoked when
`settings.interview_demo_mode` was on, and nothing served the cached JPEG
over HTTP. The live `/dashboard` camera panel therefore never showed a real
frame image.

## Decision

1. `vision_worker_impl.py` now calls `_cache_annotated_frame` unconditionally
   (every processed replay frame, ~10 fps), not only in interview-demo mode.
   The render is one OpenCV draw call on a frame already in memory; the cost
   is negligible relative to the YOLO11n/ByteTrack inference already running
   in the same loop.
2. A new `GET /api/v1/vision/frame.jpg` endpoint serves the single most
   recent cached JPEG from `app/inference/frame_cache.py`, or a typed 404
   (`CAMERA_DEGRADED`) if no frame was cached within the last 30 seconds --
   never a blank or placeholder image.
3. The frontend polls this endpoint on a fixed interval (`<img>` with a
   cache-busting query param, refetched every 1000 ms) rather than opening an
   MJPEG multipart stream or a binary WebSocket channel.

## Alternatives considered

- **MJPEG endpoint** (`multipart/x-mixed-replace`): lower latency, one
  persistent connection. Rejected for this MVP: FastAPI/Starlette MJPEG
  streaming needs a dedicated generator route, is awkward to unit-test with
  the existing `TestClient`-based suite, and doesn't degrade cleanly through
  the same typed-404 path the rest of the API uses for "unavailable" states.
- **Binary frames over the existing WebSocket hub**: would mix a high-rate
  binary channel into a hub currently used only for small JSON incident/state
  events, complicating both the reconnect-then-REST-snapshot contract
  (CLAUDE.md "WebSocket reconnect fetches a fresh REST snapshot") and the
  hub's tests.
- **Periodic REST polling of a single latest-frame endpoint (chosen)**: same
  request/response, typed-error shape as every other REST endpoint in this
  codebase; trivial to unit-test (assert `Content-Type: image/jpeg` and
  non-trivial byte length) and to browser-test (assert the loaded `<img>`
  actually decodes to a non-trivial image, not just that the tag exists).
  Costs one HTTP request per second per connected dashboard, which is
  acceptable for this single-camera, single-viewer MVP.

## Consequences

- The camera panel now shows a genuine annotated frame image alongside the
  existing structured detection list (kept as supplemental explainability,
  per the brief) and the existing SVG zone overlay (kept for when the frame
  itself is unavailable/degraded).
- Camera health and detector health remain independently reported
  (`camera_status` / `detector_status` on `/vision/latest`); the frame
  endpoint's own 404 reflects "no recent frame," which can occur even when
  the detector is healthy (e.g. right after startup, before the first frame
  is processed) and must not be interpreted as detector failure by itself.
- No change to incident-driving logic: `interview_demo_mode` still gates
  whether CV_MODEL evidence (vs. simulator ground truth) drives incidents in
  `app/services/incident_service.py`. Only frame *caching for display* is now
  unconditional.
