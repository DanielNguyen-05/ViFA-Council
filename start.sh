#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID=""
FRONTEND_PID=""
SYNC_FIRST=0

usage() {
  echo "Usage: ./start.sh [--sync]"
  echo
  echo "  --sync  Explicitly run 'uv sync' before starting services."
  echo "          Without this flag, the launcher never installs packages."
}

fail() {
  echo "Error: $*" >&2
  exit 1
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi

  if [[ -n "$FRONTEND_PID" ]]; then
    wait "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]]; then
    wait "$BACKEND_PID" 2>/dev/null || true
  fi

  exit "$exit_code"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sync)
      SYNC_FIRST=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      fail "unknown argument '$1'"
      ;;
  esac
  shift
done

cd "$PROJECT_DIR"

command -v uv >/dev/null 2>&1 || fail "uv is required. Install it from https://docs.astral.sh/uv/ and run 'uv sync'."
command -v npm >/dev/null 2>&1 || fail "npm is required. Install Node.js 22, then run 'npm install' in frontend/."

if [[ "$SYNC_FIRST" -eq 1 ]]; then
  echo "Synchronizing the backend environment because --sync was provided..."
  uv sync
elif [[ ! -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  fail "the backend environment is missing. Run 'uv sync', or rerun './start.sh --sync' to explicitly install it."
fi

if [[ ! -d "$PROJECT_DIR/frontend/node_modules" ]] || [[ ! -x "$PROJECT_DIR/frontend/node_modules/.bin/vite" ]]; then
  fail "frontend dependencies are missing. Run 'cd frontend && npm install' (or 'npm ci'), then retry."
fi

if ! uv run --no-sync python -c "import backend.main"; then
  fail "backend preflight import failed. Run 'uv sync' and review the traceback above."
fi

echo "Starting ViFA-Council backend on http://localhost:8000..."
uv run --no-sync python -m backend.main &
BACKEND_PID=$!

echo "Starting ViFA-Council frontend on http://localhost:5173..."
(
  cd "$PROJECT_DIR/frontend"
  exec npm run dev -- --host 127.0.0.1 --port 5173
) &
FRONTEND_PID=$!

# Give both processes a short opportunity to expose configuration or port errors
# before announcing a successful startup.
sleep 2

if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
  if wait "$BACKEND_PID"; then
    backend_status=0
  else
    backend_status=$?
  fi
  fail "backend exited during startup with status $backend_status."
fi

if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
  if wait "$FRONTEND_PID"; then
    frontend_status=0
  else
    frontend_status=$?
  fi
  fail "frontend exited during startup with status $frontend_status."
fi

echo
echo "ViFA-Council is running."
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo "Press Ctrl+C to stop both services."

while true; do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    if wait "$BACKEND_PID"; then
      backend_status=0
    else
      backend_status=$?
    fi
    fail "backend stopped unexpectedly with status $backend_status."
  fi

  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    if wait "$FRONTEND_PID"; then
      frontend_status=0
    else
      frontend_status=$?
    fi
    fail "frontend stopped unexpectedly with status $frontend_status."
  fi

  sleep 1
done
