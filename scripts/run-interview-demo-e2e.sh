#!/usr/bin/env bash
# Starts a throwaway backend + frontend on non-default ports, with the vision
# worker pointed at the real interview compilation and CV_MODEL-driven
# incidents enabled, runs the Playwright interview-demo e2e test against
# them, and tears both down on exit. Mirrors scripts/run-e2e.sh's structure.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT=8124
FRONTEND_PORT=5184
DB_PATH="$ROOT_DIR/backend/data/e2e-interview-demo.db"
VIDEO_PATH="$ROOT_DIR/demo-assets/interview_compilation_source.mp4"

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
  rm -f "$DB_PATH"
}
trap cleanup EXIT

if [[ ! -f "$VIDEO_PATH" ]]; then
  echo "ERROR: $VIDEO_PATH not found. See demo-assets/INTERVIEW_VIDEO_SOURCES.md." >&2
  exit 1
fi

kill_port "$BACKEND_PORT"
kill_port "$FRONTEND_PORT"

rm -f "$DB_PATH"
cd "$ROOT_DIR/backend"
SENTINEL_DATABASE_URL="sqlite:///$DB_PATH" .venv/bin/python -m alembic upgrade head
SENTINEL_DATABASE_URL="sqlite:///$DB_PATH" \
SENTINEL_INTERVIEW_DEMO_MODE=1 \
SENTINEL_VISION_REPLAY_PATH="$VIDEO_PATH" \
SENTINEL_CORS_ORIGINS="[\"http://127.0.0.1:$FRONTEND_PORT\",\"http://localhost:$FRONTEND_PORT\"]" \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" \
  > /tmp/sentinel-interview-e2e-backend.log 2>&1 &
BACKEND_PID=$!

cd "$ROOT_DIR/frontend"
VITE_API_BASE="http://127.0.0.1:$BACKEND_PORT/api/v1" VITE_WS_BASE="ws://127.0.0.1:$BACKEND_PORT/api/v1/ws" \
  npm run dev -- --port "$FRONTEND_PORT" --strictPort > /tmp/sentinel-interview-e2e-frontend.log 2>&1 &

timeout 30 bash -c "until curl -sf http://127.0.0.1:$BACKEND_PORT/api/v1/health/live >/dev/null; do sleep 1; done"
timeout 30 bash -c "until curl -sf http://127.0.0.1:$FRONTEND_PORT/ >/dev/null; do sleep 1; done"

E2E_API_BASE="http://127.0.0.1:$BACKEND_PORT/api/v1" E2E_APP_BASE="http://127.0.0.1:$FRONTEND_PORT" \
  node tests/e2e/interview-demo.e2e.mjs
