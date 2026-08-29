# Interview-compilation demo (specification, not yet runnable end-to-end)

`make interview-demo` exists as a **guard target** today, not a working demo.
No genuinely licensed continuous "interview compilation" video has been
sourced for this project (see `docs/adr/0002-vision-v2-roadmap.md` §3) —
running the target against a clean checkout correctly and intentionally fails
with a clear message pointing here, rather than silently running the bundled
still-image slideshow (`demo-assets/replay.mp4`) and presenting it as
continuous footage.

This document specifies the sequence a future contributor should implement
and run once real, licensed footage exists at
`demo-assets/interview_compilation_source.mp4` (see the acquisition
checklist in the ADR).

## Prerequisites (checked by `make interview-demo` today)

1. Vision dependencies installed (`make setup-vision`) — the target checks
   `import torch, ultralytics` and fails immediately with the exact command
   to run if either is missing.
2. `demo-assets/interview_compilation_source.mp4` present — the target checks
   this file's existence and fails immediately (pointing here) if absent.

## Intended sequence, once real video is available

1. **Verify dependencies** — `make setup-vision` completed; `torch` and
   `ultralytics` importable.
2. **Verify checksums** — the PPE detector artifact
   (`models/artifacts/ppe-yolo11n.pt`) matches `models/registry.json`'s
   recorded sha256 (same check `app/inference/vision_worker_impl.load_model`
   already performs before every demo run — no separate step needed, but
   this demo should surface the result rather than silently degrading).
3. **Start backend and frontend** — `make demo` (or the equivalent manual
   `uvicorn`/`npm run dev` commands), confirming `/health` reports the
   detector status.
4. **Load zones** — confirm `GET /api/v1/vision/zones` returns the configured
   gas-exposure/overhead-work/mandatory-vest/restricted polygons (the same
   versioned config used by the simulator-driven demo).
5. **Process the compilation through the real detector/tracker** — point the
   vision worker at `demo-assets/interview_compilation_source.mp4` (a
   dedicated adapter path, or a temporary override of
   `SENTINEL_VISION_REPLAY_PATH`) so YOLO11n + ByteTrack run against the real
   continuous footage instead of the bundled slideshow.
6. **Generate alerts** — verify PPE/zone dwell rules fire against sustained
   multi-frame tracking (this is the main thing a continuous clip adds over
   the current still-image replay: identity persistence across frames).
7. **Save evidence** — confirm `backend/data/incident-evidence/` receives one
   annotated evidence image per newly opened/escalated incident (the same
   mechanism documented for the simulator-driven demo in
   `docs/README.md`/`docs/ACCEPTANCE_RESULTS.md`), and note explicitly
   whether the CV_MODEL evidence path is wired into incident logic for this
   specific demo (it is NOT for the simulator-driven `/dashboard` demo — see
   `app/services/incident_service.py`'s `_latest_vision_rows` comment on why
   only `SIMULATION_GROUND_TRUTH` drives incidents there).
8. **Stream to the dashboard** — confirm the camera panel on `/dashboard`
   shows the real annotated detections with correct provenance labelling
   (`CV_MODEL`, never presented as simulation ground truth or vice versa).
9. **Clean shutdown** — `make demo-stop`; confirm no orphaned processes hold
   port 8000/5173 (existing `demo-stop` behavior, see `Makefile`).

## What this document does NOT claim

- It does not claim any of the above has been executed end-to-end in this
  project. `make interview-demo`'s current, verified behavior is: refuse to
  run and point here, because no real video is bundled.
- It does not claim a fake/placeholder video was created to make the target
  "pass" — that would misrepresent the demo's provenance, which CLAUDE.md's
  invariant #2 (evidence provenance) forbids.
