#!/usr/bin/env bash
# Backend :8080 + frontend dev server :3000 (both background).
# Usage: myrm start
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib/resolve_agent_root.sh
source "${REPO_ROOT}/scripts/lib/resolve_agent_root.sh"
# shellcheck source=lib/backend_bg.sh
source "${SCRIPT_DIR}/lib/backend_bg.sh"
resolve_agent_paths "${REPO_ROOT}"

FRONTEND_PID="${FRONTEND_DIR}/.myrm-dev-frontend.pid"
FRONTEND_LOG="${FRONTEND_DIR}/.myrm-dev-frontend.log"
APP_URL="http://localhost:3000"

if ! command -v bun >/dev/null 2>&1; then
  echo "ERROR: bun not found. Run: myrm setup" >&2
  exit 1
fi

if ! _start_backend_bg "${SERVER_DIR}"; then
  exit 1
fi
echo "✅ Backend http://127.0.0.1:8080"

if [[ -f "${FRONTEND_PID}" ]]; then
  old_fp="$(cat "${FRONTEND_PID}")"
  if kill -0 "${old_fp}" 2>/dev/null; then
    echo "✅ Frontend already running → ${APP_URL}"
    exit 0
  fi
  rm -f "${FRONTEND_PID}"
fi

cd "${FRONTEND_DIR}"
nohup bun run dev >>"${FRONTEND_LOG}" 2>&1 &
echo $! >"${FRONTEND_PID}"

echo "🚀 Frontend starting (log: ${FRONTEND_LOG})"
for _ in $(seq 1 60); do
  if curl -sf "${APP_URL}" >/dev/null 2>&1; then
    echo "✅ Open ${APP_URL}"
    echo "   Stop: myrm stop"
    exit 0
  fi
  sleep 1
done

echo "⚠️  Frontend slow to start; check ${FRONTEND_LOG}. Try ${APP_URL} shortly." >&2
exit 0
