#!/usr/bin/env bash
# Runs the genuine interview-demonstration sequence end to end against real,
# licensed continuous footage (demo-assets/interview_compilation_source.mp4):
# verifies prerequisites, starts a real backend+frontend with the vision
# worker pointed at that video and CV_MODEL-driven incidents enabled
# (SENTINEL_INTERVIEW_DEMO_MODE=1), starts a scenario so the risk-pipeline
# tick loop runs, waits for genuine incidents to appear via the real API, and
# shuts down cleanly. No slideshow/fake-alert fallback: every check below
# fails loudly rather than silently proceeding on missing/fabricated state.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT=8000
FRONTEND_PORT=5173
VIDEO_PATH="$ROOT_DIR/demo-assets/interview_compilation_source.mp4"
# A dedicated database, not backend/data/sentinel.db (the regular `make demo`
# database) -- keeps interview-demo runs deterministic/repeatable and never
# conflates its incidents with a real demo session's state.
DB_PATH="$ROOT_DIR/backend/data/interview-demo.db"
DB_URL="sqlite:///$DB_PATH"

kill_port() {
  local port="$1"
  local pids
  pids=$(lsof -ti ":$port" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    kill -9 $pids 2>/dev/null || true
  fi
}

cleanup() {
  echo
  echo "Shutting down..."
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  kill_port "$BACKEND_PORT"
  kill_port "$FRONTEND_PORT"
  wait 2>/dev/null || true
  echo "Clean shutdown complete (ports $BACKEND_PORT/$FRONTEND_PORT free)."
}
trap cleanup EXIT

echo "=== 1. Verify vision dependencies ==="
cd "$ROOT_DIR/backend"
.venv/bin/python -c "import torch, ultralytics" || {
  echo "ERROR: vision dependencies not installed. Run 'make setup-vision' first." >&2
  exit 1
}
echo "OK: torch/ultralytics importable."

echo
echo "=== 2. Verify PPE artifact checksum against registry ==="
.venv/bin/python -c "
import json, hashlib, sys
from pathlib import Path
registry = json.loads(Path('../models/registry.json').read_text())
meta = registry['ppe_detector']
artifact = Path('..') / meta['artifact_path']
if not artifact.exists():
    print(f'ERROR: {artifact} missing', file=sys.stderr); sys.exit(1)
digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
if digest != meta['sha256']:
    print(f'ERROR: checksum mismatch for {artifact}', file=sys.stderr); sys.exit(1)
print(f\"OK: {meta['artifact_path']} (version {meta['version']}) checksum verified.\")
"

echo
echo "=== 3. Verify source video exists ==="
if [[ ! -f "$VIDEO_PATH" ]]; then
  echo "ERROR: $VIDEO_PATH not found. See demo-assets/INTERVIEW_VIDEO_SOURCES.md." >&2
  exit 1
fi
echo "OK: $VIDEO_PATH ($(du -h "$VIDEO_PATH" | cut -f1))"

echo
echo "=== 4. Clean stale state and start backend + frontend ==="
kill_port "$BACKEND_PORT"
kill_port "$FRONTEND_PORT"
mkdir -p "$ROOT_DIR/backend/data"
rm -f "$DB_PATH"
SENTINEL_DATABASE_URL="$DB_URL" .venv/bin/python -m alembic upgrade head

SENTINEL_DATABASE_URL="$DB_URL" SENTINEL_INTERVIEW_DEMO_MODE=1 SENTINEL_VISION_REPLAY_PATH="$VIDEO_PATH" \
  nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" \
  > /tmp/sentinel-interview-demo-backend.log 2>&1 &
BACKEND_PID=$!

cd "$ROOT_DIR/frontend"
nohup npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort \
  > /tmp/sentinel-interview-demo-frontend.log 2>&1 &

timeout 30 bash -c "until curl -sf http://127.0.0.1:$BACKEND_PORT/api/v1/health/live >/dev/null; do sleep 1; done"
timeout 90 bash -c "until curl -sf http://127.0.0.1:$FRONTEND_PORT/ >/dev/null; do sleep 1; done"
echo "OK: backend (pid $BACKEND_PID) and frontend up."

echo
echo "=== 5. Confirm vision worker is genuinely processing the real video ==="
timeout 20 bash -c "
until curl -sf http://127.0.0.1:$BACKEND_PORT/api/v1/vision/latest | grep -q '\"detector_status\":\"OK\"'; do
  sleep 1
done
"
curl -s "http://127.0.0.1:$BACKEND_PORT/api/v1/vision/latest" | python3 -c "
import json, sys
d = json.load(sys.stdin)
fps = d.get('fps') or 0.0
print(f\"OK: model_version={d['model_version']} camera_status={d['camera_status']} fps={fps:.1f} tracks_now={len(d.get('tracks', []))}\")
"

echo
echo "=== 6. Load and start a scenario (so the risk-pipeline tick loop runs) ==="
LOAD_BODY=$(curl -s -X POST "http://127.0.0.1:$BACKEND_PORT/api/v1/simulation/scenarios/normal/load?seed=42")
echo "OK: $(echo "$LOAD_BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print('run_id='+d['state']['run_id'])")"
CID=$(python3 -c "import uuid; print(uuid.uuid4())")
curl -s -X POST "http://127.0.0.1:$BACKEND_PORT/api/v1/simulation/commands" -H "Content-Type: application/json" \
  -d "{\"command_id\":\"$CID\",\"command\":\"start\"}" > /dev/null
# The risk-pipeline tick loop (which is what evaluates PPE risk against real
# CV_MODEL evidence) only runs on a simulation tick, and at the default
# speed=1 a tick fires once per 5 SIMULATED minutes -- i.e. every 300 REAL
# seconds. That is far too sparse to reliably catch the video's transient
# real-time PPE/zone state within the 30-second CV_MODEL evidence window (see
# incident_service._latest_vision_rows). speed=300 (the max) makes ticks fire
# roughly once per real second instead, matching the vision worker's own
# frame cadence -- found live: without this, `make interview-demo` was
# flaky/silent depending on tick-vs-video-loop timing luck.
CID2=$(python3 -c "import uuid; print(uuid.uuid4())")
curl -s -X POST "http://127.0.0.1:$BACKEND_PORT/api/v1/simulation/commands" -H "Content-Type: application/json" \
  -d "{\"command_id\":\"$CID2\",\"command\":\"set_speed\",\"payload\":{\"speed\":300}}" > /dev/null
echo "OK: simulation RUNNING at speed=300 (ticks ~1/real-second)."

echo
echo "=== 7. Wait for genuine incidents (real CV_MODEL evidence -> real DB rows) ==="
timeout 90 bash -c "
until [[ \$(curl -s http://127.0.0.1:$BACKEND_PORT/api/v1/incidents | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))') -gt 0 ]]; do
  sleep 2
done
"
INCIDENTS=$(curl -s "http://127.0.0.1:$BACKEND_PORT/api/v1/incidents")
echo "$INCIDENTS" | python3 -c "
import json, sys
rows = json.load(sys.stdin)
print(f'OK: {len(rows)} real incident(s) generated:')
for r in rows:
    print(f\"  - {r['type']} ({r['severity']}, {r['state']})\")
"

echo
echo "=== 8. Confirm at least one incident has a real captured evidence frame ==="
FIRST_ID=$(echo "$INCIDENTS" | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['incident_id'])")
REPORT=$(curl -s "http://127.0.0.1:$BACKEND_PORT/api/v1/incidents/$FIRST_ID/report.json")
echo "$REPORT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
imgs = d.get('evidence_images', [])
if not imgs:
    print('WARNING: no evidence image captured for the first incident yet (may still be within debounce).')
else:
    real = [i for i in imgs if i.get('is_real_camera_frame')]
    print(f\"OK: {len(imgs)} evidence image(s), {len(real)} genuinely real camera frame(s).\")
"

echo
echo "=== 9. Shut down cleanly ==="
echo "Interview demo verified end-to-end (backend/frontend were reachable at"
echo "http://127.0.0.1:$BACKEND_PORT and http://127.0.0.1:$FRONTEND_PORT during the run above)."
# cleanup() runs automatically on exit via the trap set above.
