#!/usr/bin/env bash
# Starts a real backend+frontend against the real interview-demo video
# (interview_demo_mode on), runs scripts/capture_demo_assets.mjs to produce
# the 12 required screenshots and the full screen-recording deliverable from
# one continuous, genuine Playwright session, converts the raw .webm to the
# final mp4, and tears both servers down.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT=8125
FRONTEND_PORT=5185
DB_PATH="$ROOT_DIR/backend/data/capture-demo.db"
VIDEO_PATH="$ROOT_DIR/demo-assets/interview_compilation_source.mp4"
CAPTURE_VIDEO_DIR="/tmp/sentinel-capture-video"

kill_port() {
  local port="$1"
  local pids
  pids=$(lsof -ti ":$port" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    kill -9 $pids 2>/dev/null || true
  fi
}

cleanup() {
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  kill_port "$BACKEND_PORT"
  kill_port "$FRONTEND_PORT"
  wait 2>/dev/null || true
}
trap cleanup EXIT

if [[ ! -f "$VIDEO_PATH" ]]; then
  echo "ERROR: $VIDEO_PATH not found." >&2
  exit 1
fi

kill_port "$BACKEND_PORT"
kill_port "$FRONTEND_PORT"
rm -rf "$CAPTURE_VIDEO_DIR"
mkdir -p "$CAPTURE_VIDEO_DIR"
rm -f "$DB_PATH"

cd "$ROOT_DIR/backend"
SENTINEL_DATABASE_URL="sqlite:///$DB_PATH" .venv/bin/python -m alembic upgrade head
SENTINEL_DATABASE_URL="sqlite:///$DB_PATH" \
SENTINEL_INTERVIEW_DEMO_MODE=1 \
SENTINEL_VISION_REPLAY_PATH="$VIDEO_PATH" \
SENTINEL_CORS_ORIGINS="[\"http://127.0.0.1:$FRONTEND_PORT\",\"http://localhost:$FRONTEND_PORT\"]" \
  nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" \
  > /tmp/sentinel-capture-backend.log 2>&1 &
BACKEND_PID=$!

cd "$ROOT_DIR/frontend"
VITE_API_BASE="http://127.0.0.1:$BACKEND_PORT/api/v1" VITE_WS_BASE="ws://127.0.0.1:$BACKEND_PORT/api/v1/ws" \
  nohup npm run dev -- --port "$FRONTEND_PORT" --strictPort > /tmp/sentinel-capture-frontend.log 2>&1 &

timeout 30 bash -c "until curl -sf http://127.0.0.1:$BACKEND_PORT/api/v1/health/live >/dev/null; do sleep 1; done"
timeout 30 bash -c "until curl -sf http://127.0.0.1:$FRONTEND_PORT/ >/dev/null; do sleep 1; done"

cd "$ROOT_DIR/frontend"
CAPTURE_API_BASE="http://127.0.0.1:$BACKEND_PORT/api/v1" \
CAPTURE_APP_BASE="http://127.0.0.1:$FRONTEND_PORT" \
CAPTURE_SCREENSHOT_DIR="$ROOT_DIR/docs/screenshots/final" \
CAPTURE_VIDEO_DIR="$CAPTURE_VIDEO_DIR" \
CAPTURE_FINAL_VIDEO="$ROOT_DIR/deliverables/Factory_Safety_Sentinel_Interview_Demo.mp4" \
  node scripts/capture_demo_assets.mjs

RAW_WEBM=$(find "$CAPTURE_VIDEO_DIR" -name "*__raw.webm" | head -1)
if [[ -n "$RAW_WEBM" ]]; then
  mkdir -p "$ROOT_DIR/deliverables"
  ffmpeg -y -i "$RAW_WEBM" -c:v libx264 -crf 22 -preset medium -pix_fmt yuv420p -movflags +faststart \
    "$ROOT_DIR/deliverables/Factory_Safety_Sentinel_Interview_Demo.mp4"
  echo "Wrote $ROOT_DIR/deliverables/Factory_Safety_Sentinel_Interview_Demo.mp4"
else
  echo "ERROR: no raw recording found in $CAPTURE_VIDEO_DIR" >&2
  exit 1
fi

echo "Screenshots in $ROOT_DIR/docs/screenshots/final/:"
ls -la "$ROOT_DIR/docs/screenshots/final/"
