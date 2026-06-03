#!/usr/bin/env bash
# Start backend in background, wait for /health, then print frontend dev hint.
#
# Usage (from myrm-agent repo root):
#   myrm dev
#   myrm dev --foreground   # same as myrm start (blocking)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib/resolve_agent_root.sh
source "${REPO_ROOT}/scripts/lib/resolve_agent_root.sh"
# shellcheck source=../lib/start_server.sh
source "${REPO_ROOT}/scripts/lib/start_server.sh"
resolve_agent_paths "${REPO_ROOT}"

PID_FILE="${SERVER_DIR}/.myrm-dev-backend.pid"
LOG_FILE="${SERVER_DIR}/.myrm-dev-backend.log"
HEALTH_URL="http://127.0.0.1:8080/api/v1/health"

if [[ "${1:-}" == "--foreground" ]]; then
  exec start_myrm_server "${SERVER_DIR}"
fi

if [[ -f "${PID_FILE}" ]]; then
  old_pid="$(cat "${PID_FILE}")"
  if kill -0 "${old_pid}" 2>/dev/null; then
    echo "ℹ️  Dev backend already running (pid ${old_pid}). Log: ${LOG_FILE}"
    echo "   Stop: myrm stop"
    echo "   Frontend: cd myrm-agent-frontend && bun run dev  →  http://localhost:3000"
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

py=""
if [[ -x "${SERVER_DIR}/.venv/bin/python" ]]; then
  py="${SERVER_DIR}/.venv/bin/python"
elif [[ -x "${SERVER_DIR}/.venv/Scripts/python.exe" ]]; then
  py="${SERVER_DIR}/.venv/Scripts/python.exe"
fi
if [[ -z "${py}" ]]; then
  echo "ERROR: no .venv python. Run: myrm setup" >&2
  exit 1
fi

export DEPLOY_MODE="${DEPLOY_MODE:-local}"
export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-8080}"

cd "${SERVER_DIR}"
nohup "${py}" run.py >>"${LOG_FILE}" 2>&1 &
echo $! >"${PID_FILE}"

echo "🚀 Dev backend starting (pid $(cat "${PID_FILE}"), log: ${LOG_FILE})"
for _ in $(seq 1 45); do
  if curl -sf "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "✅ Backend ready at ${HEALTH_URL%/api/v1/health}"
    echo ""
    echo "Next (this or another terminal):"
    echo "  cd myrm-agent-frontend && bun run dev"
    echo "  → http://localhost:3000"
    exit 0
  fi
  sleep 1
done

echo "⚠️  Backend did not respond on :8080 within 45s. Check ${LOG_FILE}" >&2
exit 1
